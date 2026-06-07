"""Shared helpers for resolving retrieval scan context."""

from __future__ import annotations

import sqlite3


def resolve_repo_and_scan_run(
    connection: sqlite3.Connection,
    repo_id: str | None = None,
) -> tuple[str, str]:
    """Resolve the repo id and latest successful scan run for retrieval."""

    if repo_id:
        row = connection.execute(
            """
            SELECT id
            FROM scan_runs
            WHERE repo_id = ? AND status = 'done'
            ORDER BY finished_at DESC, started_at DESC
            LIMIT 1
            """,
            (repo_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No successful scan found for repo_id={repo_id}")
        return repo_id, row["id"]

    row = connection.execute(
        """
        SELECT repo_id, id
        FROM scan_runs
        WHERE status = 'done'
        ORDER BY finished_at DESC, started_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise KeyError("No successful scan available. Run `cgstudio index <path>` first.")
    return row["repo_id"], row["id"]
