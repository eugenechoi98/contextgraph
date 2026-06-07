"""SQLite schema、迁移与连接管理。"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from contextgraph_studio.config import Settings


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS repositories (
        id TEXT PRIMARY KEY,
        local_path TEXT NOT NULL UNIQUE,
        remote_url TEXT,
        default_branch TEXT,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scan_runs (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL REFERENCES repositories(id),
        commit_sha TEXT,
        started_at INTEGER NOT NULL,
        finished_at INTEGER,
        status TEXT NOT NULL,
        stats_json TEXT,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS files (
        id TEXT PRIMARY KEY,
        scan_run_id TEXT NOT NULL REFERENCES scan_runs(id),
        repo_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        language TEXT,
        category TEXT NOT NULL,
        size_bytes INTEGER,
        line_count INTEGER,
        content_hash TEXT NOT NULL,
        is_excluded INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        file_id TEXT NOT NULL REFERENCES files(id),
        repo_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        symbol_name TEXT,
        display_name TEXT,
        line_start INTEGER,
        line_end INTEGER,
        signature TEXT,
        docstring TEXT,
        language TEXT,
        content_hash TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS relations (
        id TEXT PRIMARY KEY,
        scan_run_id TEXT NOT NULL,
        from_entity_id TEXT NOT NULL REFERENCES entities(id),
        to_entity_id TEXT NOT NULL REFERENCES entities(id),
        edge_type TEXT NOT NULL,
        is_directed INTEGER DEFAULT 1,
        weight REAL DEFAULT 1.0,
        meta_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        entity_id TEXT REFERENCES entities(id),
        file_id TEXT NOT NULL REFERENCES files(id),
        repo_id TEXT NOT NULL,
        scan_run_id TEXT NOT NULL,
        chunk_kind TEXT NOT NULL,
        content TEXT NOT NULL,
        tokens_estimate INTEGER NOT NULL,
        line_start INTEGER,
        line_end INTEGER,
        content_hash TEXT NOT NULL,
        embedding_model TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS traces (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL,
        query TEXT NOT NULL,
        task_type TEXT,
        retrieval_strategy_json TEXT,
        bm25_hits_json TEXT,
        vector_hits_json TEXT,
        graph_hits_json TEXT,
        reranker_scores_json TEXT,
        final_selection_json TEXT,
        filtered_out_json TEXT,
        token_estimate INTEGER,
        latency_ms INTEGER,
        index_version TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS embeddings (
        chunk_id TEXT PRIMARY KEY REFERENCES chunks(id),
        embedding BLOB NOT NULL,
        model TEXT NOT NULL,
        dim INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS eval_runs (
        id TEXT PRIMARY KEY,
        repo_id TEXT NOT NULL,
        eval_dataset TEXT NOT NULL,
        config_json TEXT,
        results_json TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        chunk_id UNINDEXED,
        repo_id UNINDEXED,
        scan_run_id UNINDEXED,
        file_path,
        symbol_name,
        content,
        tokenize = 'porter unicode61'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_repositories_path ON repositories(local_path)",
    "CREATE INDEX IF NOT EXISTS idx_scan_runs_repo_status ON scan_runs(repo_id, status, finished_at)",
    "CREATE INDEX IF NOT EXISTS idx_files_repo_scan_path ON files(repo_id, scan_run_id, file_path)",
    "CREATE INDEX IF NOT EXISTS idx_files_hash ON files(content_hash)",
    "CREATE INDEX IF NOT EXISTS idx_entities_file ON entities(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_entities_symbol ON entities(symbol_name)",
    "CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity_id, edge_type)",
    "CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_entity_id, edge_type)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_repo_scan ON chunks(repo_id, scan_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_repo_hash ON chunks(repo_id, content_hash)",
    "CREATE INDEX IF NOT EXISTS idx_embeddings_model_dim ON embeddings(model, dim)",
    "CREATE INDEX IF NOT EXISTS idx_traces_repo_created ON traces(repo_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_eval_runs_repo_created ON eval_runs(repo_id, created_at)",
)


def connect(database_path: Path) -> sqlite3.Connection:
    """创建数据库连接。"""

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _rename_table(connection: sqlite3.Connection, old_name: str, new_name: str) -> None:
    if _table_exists(connection, old_name) and not _table_exists(connection, new_name):
        connection.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")


def _migrate_legacy_bootstrap_tables(connection: sqlite3.Connection) -> None:
    """把旧 bootstrap 表挪到 legacy 命名，避免阻塞正式 schema。"""

    if _table_exists(connection, "files") and "scan_run_id" not in _table_columns(connection, "files"):
        _rename_table(connection, "files", "files_legacy_bootstrap")
    if _table_exists(connection, "chunks") and "scan_run_id" not in _table_columns(connection, "chunks"):
        _rename_table(connection, "chunks", "chunks_legacy_bootstrap")
    if _table_exists(connection, "traces") and "repo_id" not in _table_columns(connection, "traces"):
        _rename_table(connection, "traces", "traces_legacy_bootstrap")


def _migrate_legacy_traces(connection: sqlite3.Connection) -> None:
    """把旧 trace 记录迁移到新 schema。"""

    if not _table_exists(connection, "traces_legacy_bootstrap"):
        return
    rows = connection.execute(
        """
        SELECT trace_id, query, task_type, token_budget, payload_json, created_at
        FROM traces_legacy_bootstrap
        """
    ).fetchall()
    for row in rows:
        existing = connection.execute(
            "SELECT id FROM traces WHERE id = ?",
            (row["trace_id"],),
        ).fetchone()
        if existing is not None:
            continue
        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = int(datetime.fromisoformat(created_at).timestamp())
        payload = row["payload_json"] or "{}"
        connection.execute(
            """
            INSERT INTO traces (
                id, repo_id, query, task_type, retrieval_strategy_json, bm25_hits_json,
                vector_hits_json, graph_hits_json, reranker_scores_json, final_selection_json,
                filtered_out_json, token_estimate, latency_ms, index_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["trace_id"],
                "legacy-bootstrap",
                row["query"],
                row["task_type"],
                json.dumps(["bm25"], ensure_ascii=False),
                None,
                None,
                None,
                None,
                payload,
                None,
                row["token_budget"],
                None,
                None,
                created_at,
            ),
        )


def _normalize_trace_timestamps(connection: sqlite3.Connection) -> None:
    """把历史文本时间统一成整数时间戳。"""

    rows = connection.execute(
        "SELECT id, created_at FROM traces WHERE typeof(created_at) = 'text'"
    ).fetchall()
    for row in rows:
        created_at = int(datetime.fromisoformat(row["created_at"]).timestamp())
        connection.execute(
            "UPDATE traces SET created_at = ? WHERE id = ?",
            (created_at, row["id"]),
        )


def _ensure_scan_run_error_message_column(connection: sqlite3.Connection) -> None:
    """为历史数据库补 scan_runs.error_message 列。"""

    if "error_message" not in _table_columns(connection, "scan_runs"):
        connection.execute("ALTER TABLE scan_runs ADD COLUMN error_message TEXT")


def init_db(settings: Settings) -> Path:
    """初始化数据库并执行轻量迁移。"""

    settings.ensure_directories()
    with connect(settings.database_path) as connection:
        _migrate_legacy_bootstrap_tables(connection)
        for statement in CREATE_STATEMENTS:
            connection.execute(statement)
        _ensure_scan_run_error_message_column(connection)
        _migrate_legacy_traces(connection)
        _normalize_trace_timestamps(connection)
        connection.commit()
    return settings.database_path
