import json
from pathlib import Path

from typer.testing import CliRunner

import contextgraph_studio.cli as cli_module
from contextgraph_studio.config import Settings
from contextgraph_studio.services.indexer import index_repository


runner = CliRunner()


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


def write_dataset(path: Path) -> None:
    payload = {
        "dataset": "cli_eval",
        "cases": [
            {
                "id": "case_1",
                "query": "verify token auth flow",
                "task_hint": "security_auth",
                "repo_id": None,
                "expected_files": ["auth.py"],
                "critical_files": ["auth.py"],
                "helpful_files": [],
                "intent_tags": ["retrieval"],
                "expects_tests": "implicit",
                "notes": "Smoke dataset.",
                "status": "active",
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_cli_eval_help() -> None:
    result = runner.invoke(cli_module.app, ["eval", "--help"])
    assert result.exit_code == 0
    assert "--repo-id" in result.stdout


def test_cli_eval_runs_with_selected_config_and_max_cases(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repo = tmp_path / "repo"
    build_repo(repo)
    dataset_path = tmp_path / "dataset.json"
    write_dataset(dataset_path)
    output_dir = tmp_path / "reports"
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    result = runner.invoke(
        cli_module.app,
        [
            "eval",
            "--repo-id",
            str(indexed["repo_id"]),
            "--dataset",
            str(dataset_path),
            "--config",
            "bm25_only",
            "--output-dir",
            str(output_dir),
            "--max-cases",
            "1",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["active_case_count"] == 1
    assert payload["failed_case_count"] == 0
    assert payload["configs"][0]["name"] == "bm25_only"
    assert Path(payload["json_report_path"]).exists()
    assert Path(payload["markdown_report_path"]).exists()
