from contextgraph_studio.db import connect, init_db
from contextgraph_studio.config import Settings
from contextgraph_studio.services.indexer import _insert_relation


def test_insert_relation_ignores_duplicate_stable_relation_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(data_dir=tmp_path / ".data", database_path=tmp_path / ".data" / "contextgraph.db")
    init_db(settings)

    with connect(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO repositories (id, local_path, created_at, updated_at)
            VALUES ('repo-1', 'repo', 1, 1)
            """
        )
        connection.execute(
            """
            INSERT INTO scan_runs (id, repo_id, started_at, status)
            VALUES ('scan-1', 'repo-1', 1, 'running')
            """
        )
        connection.execute(
            """
            INSERT INTO files (id, scan_run_id, repo_id, file_path, category, content_hash)
            VALUES ('file-1', 'scan-1', 'repo-1', 'file.py', 'source_code', 'hash')
            """
        )
        connection.execute(
            """
            INSERT INTO entities (id, file_id, repo_id, entity_type, symbol_name, display_name)
            VALUES ('entity-a', 'file-1', 'repo-1', 'file', 'file.py', 'file.py')
            """
        )
        connection.execute(
            """
            INSERT INTO entities (id, file_id, repo_id, entity_type, symbol_name, display_name)
            VALUES ('entity-b', 'file-1', 'repo-1', 'function', 'file.fn', 'fn')
            """
        )
        first = _insert_relation(connection, "scan-1", "entity-a", "entity-b", "contains")
        second = _insert_relation(connection, "scan-1", "entity-a", "entity-b", "contains")
        different_edge = _insert_relation(connection, "scan-1", "entity-a", "entity-b", "calls")
        connection.execute(
            """
            INSERT INTO entities (id, file_id, repo_id, entity_type, symbol_name, display_name)
            VALUES ('entity-c', 'file-1', 'repo-1', 'function', 'file.other', 'other')
            """
        )
        different_target = _insert_relation(connection, "scan-1", "entity-a", "entity-c", "contains")
        connection.execute(
            """
            INSERT INTO scan_runs (id, repo_id, started_at, status)
            VALUES ('scan-2', 'repo-1', 2, 'running')
            """
        )
        connection.execute(
            """
            INSERT INTO files (id, scan_run_id, repo_id, file_path, category, content_hash)
            VALUES ('file-2', 'scan-2', 'repo-1', 'file.py', 'source_code', 'hash')
            """
        )
        connection.execute(
            """
            INSERT INTO entities (id, file_id, repo_id, entity_type, symbol_name, display_name)
            VALUES ('entity-a-2', 'file-2', 'repo-1', 'file', 'file.py', 'file.py')
            """
        )
        connection.execute(
            """
            INSERT INTO entities (id, file_id, repo_id, entity_type, symbol_name, display_name)
            VALUES ('entity-b-2', 'file-2', 'repo-1', 'function', 'file.fn', 'fn')
            """
        )
        different_scan = _insert_relation(connection, "scan-2", "entity-a-2", "entity-b-2", "contains")
        count = connection.execute("SELECT COUNT(*) FROM relations").fetchone()[0]

    assert first is True
    assert second is False
    assert different_edge is True
    assert different_target is True
    assert different_scan is True
    assert count == 4
