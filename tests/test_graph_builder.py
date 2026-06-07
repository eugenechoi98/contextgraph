import json
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.graph.builder import build_relations_for_scan
from contextgraph_studio.services.indexer import index_repository, resolve_repo_id
from contextgraph_studio.services.intake import scan_repository


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_graph_builder_creates_contains_imports_calls_and_inherits(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "base.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    (repo / "service.py").write_text(
        "from base import Base\n\n"
        "def helper_fn():\n"
        "    return 1\n\n"
        "class AuthService(Base):\n"
        "    def helper(self):\n"
        "        return True\n\n"
        "    def verify_token(self):\n"
        "        self.helper()\n"
        "        helper_fn()\n"
        "        helper_fn()\n"
        "        helper_fn()\n"
        "        return True\n",
        encoding="utf-8",
    )

    settings = make_settings(tmp_path)
    result = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                rf.symbol_name AS from_symbol,
                rt.symbol_name AS to_symbol,
                r.edge_type,
                r.weight,
                r.meta_json
            FROM relations r
            JOIN entities rf ON rf.id = r.from_entity_id
            JOIN entities rt ON rt.id = r.to_entity_id
            WHERE r.scan_run_id = ?
            ORDER BY r.edge_type, rf.symbol_name, rt.symbol_name
            """,
            (result["scan_run_id"],),
        ).fetchall()

    edge_set = {(row["from_symbol"], row["to_symbol"], row["edge_type"]) for row in rows}
    assert ("service.py", "service", "contains") in edge_set
    assert ("service.py", "service.AuthService", "contains") in edge_set
    assert ("service.py", "service.AuthService.verify_token", "contains") in edge_set
    assert ("service.AuthService", "service.AuthService.verify_token", "contains") in edge_set
    assert ("service", "base.Base", "imports") in edge_set
    assert ("service.AuthService.verify_token", "service.AuthService.helper", "calls") in edge_set
    assert ("service.AuthService.verify_token", "service.helper_fn", "calls") in edge_set
    assert ("service.AuthService", "base.Base", "inherits") in edge_set

    helper_call = next(
        row for row in rows if row["from_symbol"] == "service.AuthService.verify_token" and row["to_symbol"] == "service.helper_fn"
    )
    assert helper_call["weight"] == 1.5
    assert json.loads(helper_call["meta_json"])["call_count"] == 3


def test_graph_builder_skips_external_imports_and_is_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "import os\n"
        "from local_mod import helper\n\n"
        "def entry():\n"
        "    return helper()\n",
        encoding="utf-8",
    )
    (repo / "local_mod.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    result = index_repository(repo, settings)

    repo_id = resolve_repo_id(repo)
    source_files = scan_repository(repo, repo_id, settings)
    with connect(settings.database_path) as connection:
        rebuilt = build_relations_for_scan(connection, repo_id, result["scan_run_id"], source_files)
        connection.commit()
        rows = connection.execute(
            """
            SELECT
                rf.symbol_name AS from_symbol,
                rt.symbol_name AS to_symbol,
                r.edge_type
            FROM relations r
            JOIN entities rf ON rf.id = r.from_entity_id
            JOIN entities rt ON rt.id = r.to_entity_id
            WHERE r.scan_run_id = ?
            """,
            (result["scan_run_id"],),
        ).fetchall()

    assert rebuilt == len(rows)
    assert ("app", "os", "imports") not in {(row["from_symbol"], row["to_symbol"], row["edge_type"]) for row in rows}
    assert ("app", "local_mod.helper", "imports") in {(row["from_symbol"], row["to_symbol"], row["edge_type"]) for row in rows}
