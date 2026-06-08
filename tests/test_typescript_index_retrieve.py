from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import get_trace, retrieve_context


FIXTURE_REPO = Path("tests/fixtures/sample_ts_repo")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_typescript_fixture_repo_indexes_and_retrieves(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    result = index_repository(FIXTURE_REPO, settings)

    assert result["file_count"] == 7
    assert result["chunk_count"] >= 8
    assert result["parse_error_count"] >= 1
    assert result["vector_index_enabled"] is False

    with connect(settings.database_path) as connection:
        file_rows = connection.execute(
            "SELECT file_path, language, category FROM files WHERE scan_run_id = ? ORDER BY file_path",
            (result["scan_run_id"],),
        ).fetchall()
        chunk_rows = connection.execute(
            "SELECT chunk_kind, content FROM chunks WHERE scan_run_id = ? ORDER BY id",
            (result["scan_run_id"],),
        ).fetchall()

    assert any(row["file_path"] == "src/auth.ts" and row["language"] == "typescript" and row["category"] == "source_code" for row in file_rows)
    assert any(row["file_path"] == "src/components/Login.tsx" and row["language"] == "tsx" for row in file_rows)
    assert any(row["file_path"] == "src/utils.js" and row["language"] == "javascript" for row in file_rows)
    assert any(row["file_path"] == "tests/auth.spec.ts" and row["category"] == "test" for row in file_rows)
    assert any(row["chunk_kind"] == "file_summary" and "exports:" in row["content"] and "imports:" in row["content"] for row in chunk_rows)
    assert any("POST /login -> loginHandler" in row["content"] for row in chunk_rows)

    pack = retrieve_context(
        "Update the login route and token verification flow",
        settings,
        top_k=8,
        task_hint="api_endpoint",
        max_tokens=4000,
        repo_id=result["repo_id"],
    )
    hit_files = [item.file_path for item in pack.required + pack.supporting]
    assert "src/routes.ts" in hit_files
    assert "src/auth.ts" in hit_files
    trace = get_trace(pack.trace_id, settings)
    assert trace["id"] == pack.trace_id
    assert trace["repo_id"] == result["repo_id"]
