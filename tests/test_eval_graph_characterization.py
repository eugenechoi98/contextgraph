import json
from pathlib import Path

import pytest

from contextgraph_studio.eval.runner import load_golden_dataset, run_eval
from contextgraph_studio.config import Settings
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
    (repo / "docs.md").write_text("# Notes\n\nLocal documentation only.\n", encoding="utf-8")


def test_load_golden_dataset_defaults_graph_expectation_to_helpful(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            {
                "dataset": "default_graph_expectation",
                "cases": [
                    {
                        "id": "case_default",
                        "query": "verify token auth flow",
                        "expected_files": ["auth.py"],
                        "critical_files": ["auth.py"],
                        "helpful_files": [],
                        "intent_tags": ["retrieval"],
                        "expects_tests": "implicit",
                        "notes": "No explicit graph expectation.",
                        "status": "active",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    dataset = load_golden_dataset(dataset_path)

    assert dataset.cases[0].graph_expectation == "helpful"


def test_load_golden_dataset_rejects_unknown_graph_expectation(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            {
                "dataset": "bad_graph_expectation",
                "cases": [
                    {
                        "id": "case_bad",
                        "query": "verify token auth flow",
                        "expected_files": ["auth.py"],
                        "critical_files": ["auth.py"],
                        "helpful_files": [],
                        "intent_tags": ["retrieval"],
                        "expects_tests": "implicit",
                        "graph_expectation": "mandatory",
                        "notes": "Invalid enum.",
                        "status": "active",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_golden_dataset(dataset_path)


def test_run_eval_reports_graph_characterization_without_changing_strict_metrics(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(
            {
                "dataset": "graph_characterization",
                "cases": [
                    {
                        "id": "required_case",
                        "query": "verify token auth flow",
                        "task_hint": "security_auth",
                        "repo_id": None,
                        "expected_files": ["auth.py"],
                        "critical_files": ["auth.py"],
                        "helpful_files": [],
                        "intent_tags": ["retrieval"],
                        "expects_tests": "implicit",
                        "graph_expectation": "required",
                        "notes": "Calls graph should help.",
                        "status": "active",
                    },
                    {
                        "id": "none_case",
                        "query": "local documentation only",
                        "task_hint": "general",
                        "repo_id": None,
                        "expected_files": ["docs.md"],
                        "critical_files": ["docs.md"],
                        "helpful_files": [],
                        "intent_tags": ["docs"],
                        "expects_tests": "none",
                        "graph_expectation": "none",
                        "notes": "Graph is optional here.",
                        "status": "active",
                    },
                    {
                        "id": "draft_case",
                        "query": "draft",
                        "task_hint": "general",
                        "repo_id": None,
                        "expected_files": ["docs.md"],
                        "critical_files": ["docs.md"],
                        "helpful_files": [],
                        "intent_tags": ["draft"],
                        "expects_tests": "none",
                        "graph_expectation": "helpful",
                        "notes": "Draft should not count.",
                        "status": "draft",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)
    result = run_eval(
        settings,
        repo_id=str(indexed["repo_id"]),
        dataset_path=dataset_path,
        config_names=["bm25_graph"],
        output_dir=tmp_path / "reports",
    )

    config_result = result.configs[0]
    assert config_result.metrics.mrr >= 0.0
    assert config_result.metrics.critical_file_hit_rate >= 0.0
    assert config_result.graph_characterization.graph_expectation_counts == {"required": 1, "helpful": 0, "none": 1}
    assert config_result.graph_characterization.graph_requested_case_count == 2
    assert config_result.graph_characterization.graph_executed_case_count == 2

    required_case = next(case for case in config_result.case_results if case.case_id == "required_case")
    none_case = next(case for case in config_result.case_results if case.case_id == "none_case")
    assert required_case.graph_expectation == "required"
    assert required_case.graph_requested is True
    assert required_case.graph_executed is True
    assert none_case.graph_expectation == "none"
    assert none_case.graph_reason is not None
