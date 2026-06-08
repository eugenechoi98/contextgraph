import json
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import retrieve_context


FIXTURE_REPO = Path("tests/fixtures/sample_structured_repo")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_structured_fixture_indexes_and_retrieves_without_sensitive_values(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    result = index_repository(FIXTURE_REPO, settings)

    assert result["file_count"] == 10
    assert result["chunk_count"] >= 7
    assert result["parse_error_count"] >= 2
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
        relation_rows = connection.execute(
            """
            SELECT rf.symbol_name AS from_symbol, rt.symbol_name AS to_symbol, r.edge_type
            FROM relations r
            JOIN entities rf ON rf.id = r.from_entity_id
            JOIN entities rt ON rt.id = r.to_entity_id
            WHERE r.scan_run_id = ?
            """,
            (result["scan_run_id"],),
        ).fetchall()

    assert any(row["file_path"] == "schema.sql" and row["category"] == "schema" and row["language"] == "sql" for row in file_rows)
    assert any(row["file_path"] == "config.json" and row["category"] == "config" and row["language"] == "json" for row in file_rows)
    assert any(row["chunk_kind"] == "schema_unit" and "public.users" in row["content"] for row in chunk_rows)
    assert any(row["chunk_kind"] == "schema_unit" and "database.host" in row["content"] for row in chunk_rows)
    assert all("super-secret-password" not in row["content"] for row in chunk_rows)
    edge_set = {(row["from_symbol"], row["to_symbol"], row["edge_type"]) for row in relation_rows}
    assert ("schema.sql", "public.users", "contains") in edge_set
    assert ("config.json", "database.host", "contains") in edge_set
    assert all(edge_type == "contains" for _, _, edge_type in edge_set)

    sql_pack = retrieve_context(
        "Update the users table email index",
        settings,
        top_k=8,
        task_hint="database",
        max_tokens=3000,
        repo_id=result["repo_id"],
    )
    sql_files = [item.file_path for item in sql_pack.required + sql_pack.supporting]
    assert "schema.sql" in sql_files or "migration.sql" in sql_files

    config_pack = retrieve_context(
        "Change the database host configuration",
        settings,
        top_k=8,
        task_hint="configuration",
        max_tokens=3000,
        repo_id=result["repo_id"],
    )
    config_text = "\n".join((item.entity or "") for item in config_pack.required + config_pack.supporting)
    config_files = [item.file_path for item in config_pack.required + config_pack.supporting]
    assert any(path in {"config.json", "settings.yaml", "pyproject.toml"} for path in config_files)
    assert "database.host" in config_text
    assert "super-secret-password" not in config_text
    assert "abc123secret" not in config_text
