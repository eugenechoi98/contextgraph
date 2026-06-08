import json
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.graph.builder import build_relations_for_scan
from contextgraph_studio.graph.traversal import graph_search
from contextgraph_studio.services.indexer import index_repository, resolve_repo_id
from contextgraph_studio.services.intake import scan_repository


FIXTURE_REPO = Path("tests/fixtures/sample_ts_repo")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def test_typescript_graph_builds_contains_imports_calls_and_route_edges(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    result = index_repository(FIXTURE_REPO, settings)

    with connect(settings.database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                rf.symbol_name AS from_symbol,
                rt.symbol_name AS to_symbol,
                r.edge_type,
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
    assert ("src/routes.ts", "src/routes::POST /login", "contains") in edge_set
    assert ("src/routes", "src/auth.loginHandler", "imports") in edge_set
    assert ("src/auth.loginHandler", "src/auth.verifyToken", "calls") in edge_set
    assert ("src/routes::POST /login", "src/auth.loginHandler", "route_to_handler") in edge_set
    route_meta = next(
        row
        for row in rows
        if row["edge_type"] == "route_to_handler"
        and row["from_symbol"] == "src/routes::POST /login"
        and row["to_symbol"] == "src/auth.loginHandler"
    )
    assert json.loads(route_meta["meta_json"])["path"] == "/login"


def test_typescript_graph_route_traversal_and_idempotent_rebuild(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    result = index_repository(FIXTURE_REPO, settings)
    repo_id = resolve_repo_id(FIXTURE_REPO.resolve())
    source_files = scan_repository(FIXTURE_REPO.resolve(), repo_id, settings)

    with connect(settings.database_path) as connection:
        rebuilt = build_relations_for_scan(connection, repo_id, result["scan_run_id"], source_files)
        connection.commit()
        rows = connection.execute("SELECT COUNT(*) AS c FROM relations WHERE scan_run_id = ?", (result["scan_run_id"],)).fetchone()

    assert rebuilt == rows["c"]

    hits = graph_search(
        settings,
        symbol="src/routes::POST /login",
        repo_id=result["repo_id"],
        edge_types=["route_to_handler"],
        max_hops=1,
    )
    assert any(item.symbol_name == "src/auth.loginHandler" for item in hits)
