from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.parsers.python_parser import PARSER_VERSION, PythonParser
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import search_bm25


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_parser_extracts_only_static_module_level_assignments() -> None:
    content = (
        "# The numeric mode to set newly-uploaded files to.\n"
        "FILE_UPLOAD_PERMISSIONS = 0o644\n"
        "DEFAULT_TIMEOUT = 30\n"
        "SETTING_NAME: str = 'safe'\n"
        "FEATURE_ENABLED = True\n"
        "ITEMS = ['a', 'b']\n"
        "DYNAMIC = compute_value()\n"
        "a, b = func()\n\n"
        "class Config:\n"
        "    CLASS_VALUE = 1\n\n"
        "def fn():\n"
        "    LOCAL_VALUE = 2\n"
        "    return LOCAL_VALUE\n"
    )

    result = PythonParser().parse("django/conf/global_settings.py", content, "file-1")
    assignments = [entity for entity in result.entities if entity.entity_type == "module_assignment"]
    symbols = {entity.symbol_name for entity in assignments}

    assert PARSER_VERSION == "python-ast-v4"
    assert "django.conf.global_settings.FILE_UPLOAD_PERMISSIONS" in symbols
    assert "django.conf.global_settings.DEFAULT_TIMEOUT" in symbols
    assert "django.conf.global_settings.SETTING_NAME" in symbols
    assert "django.conf.global_settings.FEATURE_ENABLED" in symbols
    assert "django.conf.global_settings.ITEMS" in symbols
    assert "django.conf.global_settings.DYNAMIC" not in symbols
    assert "django.conf.global_settings.CLASS_VALUE" not in symbols
    assert "django.conf.global_settings.LOCAL_VALUE" not in symbols

    upload = next(entity for entity in assignments if entity.display_name == "FILE_UPLOAD_PERMISSIONS")
    assert upload.line_start == 2
    assert upload.line_end == 2
    assert "value_type: int" in (upload.signature or "")
    assert "value_preview: 420" in (upload.signature or "")
    assert "value_source_preview: 0o644" in (upload.signature or "")
    assert "comment_context: The numeric mode to set newly-uploaded files to." in (upload.signature or "")


def test_assignment_value_safety_and_truncation() -> None:
    long_value = "x" * 140
    content = (
        "API_TOKEN = 'abc123secret'\n"
        "PASSWORD = 'plain-password'\n"
        "NORMAL_NAME = 'short-value'\n"
        f"LONG_TEXT = '{long_value}'\n"
    )

    result = PythonParser().parse("settings.py", content, "file-1")
    signatures = "\n".join(entity.signature or "" for entity in result.entities)

    assert "API_TOKEN" in signatures
    assert "PASSWORD" in signatures
    assert "redacted: true" in signatures
    assert "abc123secret" not in signatures
    assert "plain-password" not in signatures
    assert "short-value" in signatures
    assert long_value not in signatures
    assert "truncated: true" in signatures


def test_assignment_chunks_are_searchable_and_existing_symbol_chunks_remain(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "settings.py").write_text(
        "FILE_UPLOAD_PERMISSIONS = 0o644\n\n"
        "class Existing:\n"
        "    pass\n\n"
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )
    settings = make_settings(tmp_path)

    result = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        assignment_chunks = connection.execute(
            """
            SELECT c.content, e.symbol_name, e.entity_type, c.chunk_kind
            FROM chunks c
            JOIN entities e ON e.id = c.entity_id
            WHERE c.scan_run_id = ? AND e.entity_type = 'module_assignment'
            """,
            (result["scan_run_id"],),
        ).fetchall()
        hits = search_bm25(
            connection,
            "FILE_UPLOAD_PERMISSIONS",
            str(result["repo_id"]),
            str(result["scan_run_id"]),
            10,
            category="source_code",
        )
        symbol_chunks = connection.execute(
            """
            SELECT e.entity_type
            FROM chunks c
            JOIN entities e ON e.id = c.entity_id
            WHERE c.scan_run_id = ? AND c.chunk_kind = 'symbol'
            """,
            (result["scan_run_id"],),
        ).fetchall()

    assert len(assignment_chunks) == 1
    assert assignment_chunks[0]["chunk_kind"] == "symbol"
    assert assignment_chunks[0]["symbol_name"] == "settings.FILE_UPLOAD_PERMISSIONS"
    assert "entity_type: module_assignment" in assignment_chunks[0]["content"]
    assert "FILE_UPLOAD_PERMISSIONS" in assignment_chunks[0]["content"]
    assert hits[0].file_path == "settings.py"
    assert {row["entity_type"] for row in symbol_chunks} >= {"module_assignment", "class", "function"}


def test_assignment_contains_relation_only_uses_existing_edge_type(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "settings.py").write_text("FILE_UPLOAD_PERMISSIONS = 0o644\n", encoding="utf-8")
    settings = make_settings(tmp_path)

    result = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        rows = connection.execute(
            """
            SELECT rf.symbol_name AS from_symbol, rt.symbol_name AS to_symbol, r.edge_type
            FROM relations r
            JOIN entities rf ON rf.id = r.from_entity_id
            JOIN entities rt ON rt.id = r.to_entity_id
            WHERE r.scan_run_id = ?
            """,
            (result["scan_run_id"],),
        ).fetchall()

    edges = {(row["from_symbol"], row["to_symbol"], row["edge_type"]) for row in rows}
    assert ("settings", "settings.FILE_UPLOAD_PERMISSIONS", "contains") in edges
    assert {row["edge_type"] for row in rows} == {"contains"}
