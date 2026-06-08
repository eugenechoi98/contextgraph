import json
from pathlib import Path

import pytest

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.services import indexer as indexer_module
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import get_trace, retrieve_context


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_index_and_retrieve(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def gateway():\n    return 'ok'\n", encoding="utf-8")
    (repo / "README.md").write_text("# Gateway\nContextGraph gateway docs\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    init_db(settings)
    result = index_repository(repo, settings)
    assert result["file_count"] == 2
    assert result["chunk_count"] >= 2
    assert "scan_run_id" in result
    assert result["vector_index_enabled"] is False
    assert result["embedding_model"] is None

    pack = retrieve_context("gateway", settings, top_k=5, repo_id=result["repo_id"])
    assert pack.retrieval_strategy == ["bm25"]
    assert pack.required
    trace = get_trace(pack.trace_id, settings)
    assert trace["id"] == pack.trace_id
    assert trace["repo_id"] == result["repo_id"]


def test_incremental_index_and_deleted_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "auth.py"
    target.write_text("def verify_token():\n    return True\n", encoding="utf-8")
    keep = repo / "util.py"
    keep.write_text("def helper():\n    return 1\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    first = index_repository(repo, settings)
    second = index_repository(repo, settings)
    assert first["repo_id"] == second["repo_id"]

    with connect(settings.database_path) as connection:
        scan_runs = connection.execute(
            "SELECT status, stats_json FROM scan_runs WHERE repo_id = ? ORDER BY started_at",
            (first["repo_id"],),
        ).fetchall()
        assert len(scan_runs) == 2
        assert all(row["status"] == "done" for row in scan_runs)
        second_stats = json.loads(scan_runs[-1]["stats_json"])
        assert second_stats["reused_files"] == 2
        assert second_stats["changed_files"] == 0
        assert second_stats["vector_index_enabled"] is False

    target.unlink()
    third = index_repository(repo, settings)
    pack = retrieve_context("verify token", settings, repo_id=third["repo_id"])
    assert all(result.file_path != "auth.py" for result in pack.required)
    with connect(settings.database_path) as connection:
        deleted_stats_row = connection.execute(
            "SELECT stats_json FROM scan_runs WHERE id = ?",
            (third["scan_run_id"],),
        ).fetchone()
        deleted_stats = json.loads(deleted_stats_row["stats_json"])
        assert deleted_stats["deleted_files"] == 1


def test_task_hint_and_trace_index_version(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token():\n    return True\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    result = index_repository(repo, settings)
    pack = retrieve_context("verify auth flow", settings, top_k=5, task_hint="security_auth", max_tokens=8000, repo_id=result["repo_id"])
    assert pack.task_type == "security_auth"
    assert pack.token_estimate >= 0
    trace = get_trace(pack.trace_id, settings)
    assert trace["index_version"] == result["scan_run_id"]
    assert trace["retrieval_strategy_json"] == ["bm25"]


def test_failed_scan_does_not_replace_latest_successful(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token():\n    return True\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    first = index_repository(repo, settings)
    (repo / "auth.py").write_text("def verify_token():\n    return False\n", encoding="utf-8")

    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("forced failure")

    monkeypatch.setattr(indexer_module, "_index_source_file", boom)
    with pytest.raises(RuntimeError):
        index_repository(repo, settings)

    pack = retrieve_context("verify token", settings, repo_id=first["repo_id"])
    assert any(result.file_path == "auth.py" for result in pack.required + pack.supporting)
    with connect(settings.database_path) as connection:
        rows = connection.execute(
            "SELECT status FROM scan_runs WHERE repo_id = ? ORDER BY started_at",
            (first["repo_id"],),
        ).fetchall()
    assert rows[-1]["status"] == "failed"


def test_index_reports_vector_observability_when_enabled(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def gateway():\n    return 'ok'\n", encoding="utf-8")

    settings = Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
        vector_index_enabled=True,
        embedding_provider="deterministic",
        embedding_model="deterministic-sha256",
        embedding_dimension=16,
        embedding_batch_size=8,
    )
    result = index_repository(repo, settings)

    assert result["vector_index_enabled"] is True
    assert result["embedding_provider"] == "deterministic"
    assert result["embedding_model"] == "deterministic-sha256"
    assert result["embedding_revision"] is None
    assert result["embedding_dimension"] == 16
    assert int(result["embedding_count"]) == int(result["chunk_count"])
