import json
from pathlib import Path

import pytest

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.eval.runner import load_golden_dataset, run_eval
from contextgraph_studio.services.indexer import index_repository


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
        "vector_index_enabled": False,
        "hybrid_vector_enabled": False,
        "hybrid_graph_enabled": True,
        "embedding_provider": "deterministic",
        "embedding_model": "deterministic-sha256",
        "embedding_dimension": 16,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def build_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def normalize_token(token: str) -> str:\n"
        "    return token.strip()\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    cleaned = normalize_token(token)\n"
        "    return cleaned == 'ok'\n",
        encoding="utf-8",
    )
    (repo / "session.py").write_text(
        "def issue_session(user_id: str) -> str:\n"
        "    return user_id\n",
        encoding="utf-8",
    )


def write_dataset(path: Path) -> None:
    payload = {
        "dataset": "mini_eval",
        "cases": [
            {
                "id": "active_ok",
                "query": "verify token auth flow",
                "task_hint": "security_auth",
                "repo_id": None,
                "expected_files": ["auth.py"],
                "critical_files": ["auth.py"],
                "helpful_files": ["session.py"],
                "intent_tags": ["retrieval"],
                "expects_tests": "implicit",
                "graph_expectation": "required",
                "notes": "Main auth flow.",
                "status": "active",
            },
            {
                "id": "active_fail",
                "query": "verify token auth flow",
                "task_hint": "security_auth",
                "repo_id": "missing-repo",
                "expected_files": ["auth.py"],
                "critical_files": ["auth.py"],
                "helpful_files": [],
                "intent_tags": ["retrieval"],
                "expects_tests": "implicit",
                "graph_expectation": "helpful",
                "notes": "Forces a per-case failure.",
                "status": "active",
            },
            {
                "id": "draft_case",
                "query": "draft case",
                "task_hint": "general",
                "repo_id": None,
                "expected_files": ["session.py"],
                "critical_files": ["session.py"],
                "helpful_files": [],
                "intent_tags": ["draft"],
                "expects_tests": "none",
                "graph_expectation": "none",
                "notes": "Should not enter aggregate metrics.",
                "status": "draft",
            }
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_load_golden_dataset_rejects_invalid_layers(tmp_path: Path) -> None:
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text(
        json.dumps(
            {
                "dataset": "invalid",
                "cases": [
                    {
                        "id": "bad_case",
                        "query": "x",
                        "expected_files": ["auth.py"],
                        "critical_files": ["missing.py"],
                        "helpful_files": [],
                        "intent_tags": [],
                        "expects_tests": "implicit",
                        "notes": "bad",
                        "status": "active"
                    }
                ]
            },
            ensure_ascii=False
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_golden_dataset(dataset_path)


def test_run_eval_skips_draft_cases_and_records_failures(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    dataset_path = tmp_path / "dataset.json"
    write_dataset(dataset_path)
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)
    original_flags = (settings.hybrid_vector_enabled, settings.hybrid_graph_enabled)

    result = run_eval(
        settings,
        repo_id=str(indexed["repo_id"]),
        dataset_path=dataset_path,
        config_names=["bm25_only", "bm25_graph"],
        output_dir=tmp_path / "reports",
    )

    assert result.active_cases == 2
    assert result.draft_cases == 1
    assert result.vector_quality_valid is False
    assert "Deterministic embeddings" in result.vector_quality_note
    assert Path(result.json_report_path).exists()
    assert Path(result.markdown_report_path).exists()
    assert Path(result.latest_json_report_path).exists()
    assert Path(result.latest_markdown_report_path).exists()
    assert [config_result.config.name for config_result in result.configs] == ["bm25_only", "bm25_graph"]
    assert settings.hybrid_vector_enabled == original_flags[0]
    assert settings.hybrid_graph_enabled == original_flags[1]

    bm25_only, bm25_graph = result.configs
    assert bm25_only.passed_case_count == 1
    assert bm25_only.failed_case_count == 1
    assert bm25_graph.passed_case_count == 1
    assert bm25_graph.failed_case_count == 1
    assert bm25_only.config.graph_enabled is False
    assert bm25_graph.config.graph_enabled is True
    assert bm25_only.case_results[0].retrieval_strategy == ["bm25"]
    assert bm25_only.case_results[0].requested_routes == ["bm25"]
    assert bm25_only.case_results[0].executed_routes == ["bm25"]
    assert bm25_only.case_results[0].participating_routes == ["bm25"]
    assert bm25_only.case_results[0].route_diagnostics["vector"]["reason"] == "disabled_by_ablation"
    assert bm25_only.case_results[0].route_diagnostics["graph"]["reason"] == "disabled_by_ablation"
    assert bm25_only.case_results[0].graph_expectation == "required"
    assert bm25_only.graph_characterization.graph_expectation_counts == {"required": 1, "helpful": 1, "none": 0}
    assert bm25_only.graph_characterization.graph_participation_rate == 0.0
    assert bm25_graph.case_results[0].requested_routes == ["bm25", "graph"]
    assert "graph" in bm25_graph.case_results[0].executed_routes
    assert bm25_graph.graph_characterization.graph_requested_case_count == 1
    assert bm25_graph.graph_characterization.graph_executed_case_count == 1
    assert bm25_only.case_results[1].status == "failed"
    assert "No successful scan found" in (bm25_only.case_results[1].error or "")

    with connect(settings.database_path) as connection:
        row = connection.execute("SELECT * FROM eval_runs WHERE id = ?", (result.eval_run_id,)).fetchone()
    assert row is not None
    stored = json.loads(row["results_json"])
    assert stored["eval_run_id"] == result.eval_run_id


def test_init_db_creates_eval_runs_table(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)

    with connect(settings.database_path) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'eval_runs'"
        ).fetchone()
    assert row is not None
