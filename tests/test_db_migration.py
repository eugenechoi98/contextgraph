import sqlite3
from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.db import init_db


def test_old_bootstrap_db_upgrades_and_keeps_traces(tmp_path: Path) -> None:
    data_dir = tmp_path / ".data"
    data_dir.mkdir()
    database_path = data_dir / "contextgraph.db"

    conn = sqlite3.connect(database_path)
    conn.execute(
        """
        CREATE TABLE traces (
            trace_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            task_type TEXT NOT NULL,
            token_budget INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO traces (trace_id, query, task_type, token_budget, payload_json, created_at)
        VALUES ('tr_old', 'legacy query', 'general', 1000, '{}', '2026-06-07T00:00:00+00:00')
        """
    )
    conn.commit()
    conn.close()

    settings = Settings(data_dir=data_dir, database_path=database_path)
    init_db(settings)
    conn = sqlite3.connect(database_path)
    row = conn.execute("SELECT id, repo_id, query FROM traces WHERE id = 'tr_old'").fetchone()
    conn.close()
    assert row is not None
