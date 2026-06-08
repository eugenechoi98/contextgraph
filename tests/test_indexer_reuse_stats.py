import json
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.services.indexer import index_repository


def test_reused_files_keep_snapshot_parse_error_count(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    settings = Settings(data_dir=tmp_path / ".data", database_path=tmp_path / ".data" / "contextgraph.db")

    first = index_repository(repo, settings)
    second = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        rows = connection.execute(
            "SELECT id, stats_json FROM scan_runs WHERE id IN (?, ?)",
            (first["scan_run_id"], second["scan_run_id"]),
        ).fetchall()
    stats = {row["id"]: json.loads(row["stats_json"]) for row in rows}
    first_stats = stats[first["scan_run_id"]]
    second_stats = stats[second["scan_run_id"]]

    assert first_stats["parse_errors_current_scan"] == 1
    assert first_stats["parse_errors_reused"] == 0
    assert first_stats["parse_errors_total_snapshot"] == 1
    assert second_stats["reused_files"] == 1
    assert second_stats["parse_errors_current_scan"] == 0
    assert second_stats["parse_errors_reused"] == 1
    assert second_stats["parse_errors_total_snapshot"] == 1
    assert second_stats["parse_errors"] == 1
    assert second_stats["parse_error_messages"] == first_stats["parse_error_messages"]


def test_reuse_stats_recover_from_legacy_empty_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    settings = Settings(data_dir=tmp_path / ".data", database_path=tmp_path / ".data" / "contextgraph.db")

    first = index_repository(repo, settings)
    second = index_repository(repo, settings)
    with connect(settings.database_path) as connection:
        legacy_stats = json.loads(
            connection.execute("SELECT stats_json FROM scan_runs WHERE id = ?", (second["scan_run_id"],)).fetchone()[0]
        )
        legacy_stats["parse_errors"] = 0
        legacy_stats["parse_errors_current_scan"] = 0
        legacy_stats["parse_errors_reused"] = 0
        legacy_stats["parse_errors_total_snapshot"] = 0
        legacy_stats["parse_error_messages"] = []
        legacy_stats["parse_error_messages_current_scan"] = []
        legacy_stats["parse_error_messages_reused"] = []
        connection.execute(
            "UPDATE scan_runs SET stats_json = ? WHERE id = ?",
            (json.dumps(legacy_stats), second["scan_run_id"]),
        )
        connection.commit()

    third = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        third_stats = json.loads(
            connection.execute("SELECT stats_json FROM scan_runs WHERE id = ?", (third["scan_run_id"],)).fetchone()[0]
        )
    assert third_stats["parse_errors_current_scan"] == 0
    assert third_stats["parse_errors_reused"] == 1
    assert third_stats["parse_errors_total_snapshot"] == 1
    assert third_stats["parse_error_messages"] == ["broken.py:1:12: invalid syntax"]
