import json
from pathlib import Path
from uuid import uuid4

import pytest

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.services import indexer
from contextgraph_studio.services.indexer import index_repository, resolve_repo_id


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def write_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "a.py").write_text(
        "from b import helper\n\n"
        "def entry():\n"
        "    return helper()\n",
        encoding="utf-8",
    )
    (repo / "b.py").write_text(
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )


def relation_edges(settings: Settings, scan_run_id: str) -> set[tuple[str, str, str]]:
    with connect(settings.database_path) as connection:
        rows = connection.execute(
            """
            SELECT rf.symbol_name AS from_symbol, rt.symbol_name AS to_symbol, r.edge_type
            FROM relations r
            JOIN entities rf ON rf.id = r.from_entity_id
            JOIN entities rt ON rt.id = r.to_entity_id
            WHERE r.scan_run_id = ?
            """,
            (scan_run_id,),
        ).fetchall()
    return {(row["from_symbol"], row["to_symbol"], row["edge_type"]) for row in rows}


def scan_stats(settings: Settings, scan_run_id: str) -> dict[str, object]:
    with connect(settings.database_path) as connection:
        row = connection.execute(
            "SELECT stats_json FROM scan_runs WHERE id = ?",
            (scan_run_id,),
        ).fetchone()
    return json.loads(row["stats_json"])


def test_unchanged_index_bulk_copies_relations_without_graph_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    write_repo(repo)
    settings = make_settings(tmp_path)

    first = index_repository(repo, settings)
    first_edges = relation_edges(settings, str(first["scan_run_id"]))

    def fail_rebuild(*args: object, **kwargs: object) -> int:
        raise AssertionError("unchanged reuse should not rebuild relations")

    monkeypatch.setattr(indexer, "build_relations_for_scan", fail_rebuild)
    second = index_repository(repo, settings)
    second_stats = scan_stats(settings, str(second["scan_run_id"]))

    assert relation_edges(settings, str(second["scan_run_id"])) == first_edges
    assert second_stats["reused_file_count"] == 2
    assert second_stats["parsed_file_count"] == 0
    assert second_stats["reused_relation_count"] == len(first_edges)
    assert second_stats["generated_relation_count"] == 0
    assert "copy reused relations" in second_stats["stage_timings_ms"]
    assert "rebuild changed relations" not in second_stats["stage_timings_ms"]


def test_changed_file_keeps_snapshot_correct_and_uses_latest_successful_scan(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_repo(repo)
    settings = make_settings(tmp_path)

    first = index_repository(repo, settings)
    (repo / "b.py").write_text(
        "def helper():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    second = index_repository(repo, settings)
    second_stats = scan_stats(settings, str(second["scan_run_id"]))

    assert second_stats["reused_file_count"] == 1
    assert second_stats["parsed_file_count"] == 1
    assert second_stats["changed_files"] == 1
    assert second_stats["generated_relation_count"] == len(relation_edges(settings, str(second["scan_run_id"])))
    assert relation_edges(settings, str(second["scan_run_id"])) == relation_edges(settings, str(first["scan_run_id"]))


def test_deleted_file_relations_do_not_enter_new_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_repo(repo)
    settings = make_settings(tmp_path)

    index_repository(repo, settings)
    (repo / "b.py").unlink()
    second = index_repository(repo, settings)

    assert all("b.py" not in edge for edge in relation_edges(settings, str(second["scan_run_id"])))
    assert all("b.helper" not in edge for edge in relation_edges(settings, str(second["scan_run_id"])))


def test_failed_scan_is_not_used_as_reuse_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_repo(repo)
    settings = make_settings(tmp_path)

    first = index_repository(repo, settings)
    repo_id = resolve_repo_id(repo)
    with connect(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO scan_runs (id, repo_id, commit_sha, started_at, finished_at, status, stats_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), repo_id, None, 999999, 999999, "failed", "{}"),
        )
        connection.commit()

    second = index_repository(repo, settings)

    assert relation_edges(settings, str(second["scan_run_id"])) == relation_edges(settings, str(first["scan_run_id"]))
    assert scan_stats(settings, str(second["scan_run_id"]))["reused_file_count"] == 2


def test_bulk_relation_copy_dedupes_and_preserves_different_edges(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_repo(repo)
    settings = make_settings(tmp_path)

    first = index_repository(repo, settings)
    with connect(settings.database_path) as connection:
        pair = connection.execute(
            """
            SELECT from_entity_id, to_entity_id
            FROM relations
            WHERE scan_run_id = ?
            LIMIT 1
            """,
            (first["scan_run_id"],),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO relations (id, scan_run_id, from_entity_id, to_entity_id, edge_type, is_directed, weight, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), first["scan_run_id"], pair["from_entity_id"], pair["to_entity_id"], "imports", 1, 2.0, None),
        )
        connection.commit()

    second = index_repository(repo, settings)
    edges = relation_edges(settings, str(second["scan_run_id"]))

    assert len(edges) == scan_stats(settings, str(second["scan_run_id"]))["reused_relation_count"]
    assert any(edge_type == "imports" for _, _, edge_type in edges)


def test_parse_error_reuse_stats_keep_current_reused_and_total_meaning(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    settings = make_settings(tmp_path)

    first = index_repository(repo, settings)
    second = index_repository(repo, settings)
    first_stats = scan_stats(settings, str(first["scan_run_id"]))
    second_stats = scan_stats(settings, str(second["scan_run_id"]))

    assert first_stats["parse_errors_current_scan"] == 1
    assert first_stats["parse_errors_reused"] == 0
    assert second_stats["parse_errors_current_scan"] == 0
    assert second_stats["parse_errors_reused"] == 1
    assert second_stats["parse_errors_total_snapshot"] == 1
