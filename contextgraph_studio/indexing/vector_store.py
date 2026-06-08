"""SQLite 向量派生层。"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from contextgraph_studio.config import Settings
from contextgraph_studio.indexing.embedder import build_embedding_provider


@dataclass(slots=True)
class VectorSyncStats:
    """向量同步统计。"""

    reused_embeddings: int = 0
    generated_embeddings: int = 0
    orphan_embeddings_removed: int = 0


def build_embedding_fingerprint(provider_name: str, model_name: str, revision: str | None = None) -> str:
    """构造 provider 作用域内的模型标识。"""

    if revision:
        return f"{provider_name}::{model_name}@{revision}"
    return f"{provider_name}::{model_name}"


def split_embedding_fingerprint(fingerprint: str) -> tuple[str, str]:
    """拆解 provider/model 指纹。"""

    if "::" not in fingerprint:
        return "unknown", fingerprint
    return tuple(fingerprint.split("::", 1))  # type: ignore[return-value]


def serialize_embedding(vector: Sequence[float], expected_dim: int) -> bytes:
    """把向量序列编码为 float32 BLOB。"""

    if expected_dim <= 0:
        raise ValueError(f"Embedding dimension must be positive, got {expected_dim}.")
    array = np.asarray(vector, dtype=np.float32)
    if array.ndim != 1:
        raise ValueError("Embedding vector must be one-dimensional.")
    if array.shape[0] != expected_dim:
        raise ValueError(f"Embedding vector dimension {array.shape[0]} does not match expected {expected_dim}.")
    return array.tobytes()


def deserialize_embedding(blob: bytes, expected_dim: int) -> np.ndarray:
    """把 float32 BLOB 还原为 numpy 向量。"""

    if expected_dim <= 0:
        raise ValueError(f"Embedding dimension must be positive, got {expected_dim}.")
    if len(blob) % np.dtype(np.float32).itemsize != 0:
        raise ValueError("Embedding blob byte length is not aligned to float32.")
    vector = np.frombuffer(blob, dtype=np.float32)
    if vector.shape[0] != expected_dim:
        raise ValueError(
            f"Embedding blob restored dimension {vector.shape[0]} does not match expected {expected_dim}."
        )
    return vector


def upsert_embedding_blob(
    connection: sqlite3.Connection,
    chunk_id: str,
    embedding_blob: bytes,
    model_fingerprint: str,
    dimension: int,
) -> None:
    """写入或更新单个 embedding BLOB。"""

    connection.execute(
        """
        INSERT INTO embeddings (chunk_id, embedding, model, dim)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
            embedding = excluded.embedding,
            model = excluded.model,
            dim = excluded.dim
        """,
        (chunk_id, embedding_blob, model_fingerprint, dimension),
    )


def delete_embeddings_for_chunks(connection: sqlite3.Connection, chunk_ids: Sequence[str]) -> int:
    """按 chunk_id 删除 embeddings。"""

    if not chunk_ids:
        return 0
    placeholders = ", ".join("?" for _ in chunk_ids)
    cursor = connection.execute(
        f"DELETE FROM embeddings WHERE chunk_id IN ({placeholders})",
        list(chunk_ids),
    )
    return int(cursor.rowcount or 0)


def prune_orphan_embeddings(connection: sqlite3.Connection) -> int:
    """清理不再关联 chunks 的孤儿 embeddings。"""

    cursor = connection.execute(
        """
        DELETE FROM embeddings
        WHERE chunk_id NOT IN (SELECT id FROM chunks)
        """
    )
    return int(cursor.rowcount or 0)


def list_embeddings_for_scan(
    connection: sqlite3.Connection,
    repo_id: str,
    scan_run_id: str,
    model_fingerprint: str,
    dimension: int,
) -> list[sqlite3.Row]:
    """读取指定 scan 的向量数据。"""

    return connection.execute(
        """
        SELECT
            c.id AS chunk_id,
            c.entity_id,
            c.chunk_kind,
            c.line_start,
            c.line_end,
            c.tokens_estimate,
            c.content,
            f.file_path,
            f.category,
            e.symbol_name AS entity,
            e.entity_type,
            emb.embedding,
            emb.model,
            emb.dim
        FROM chunks c
        JOIN files f ON f.id = c.file_id
        LEFT JOIN entities e ON e.id = c.entity_id
        JOIN embeddings emb ON emb.chunk_id = c.id
        WHERE c.repo_id = ?
          AND c.scan_run_id = ?
          AND emb.model = ?
          AND emb.dim = ?
        ORDER BY c.id
        """,
        (repo_id, scan_run_id, model_fingerprint, dimension),
    ).fetchall()


def count_embeddings_for_scan(connection: sqlite3.Connection, repo_id: str, scan_run_id: str) -> int:
    """统计某次 scan 的 embedding 总数。"""

    row = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM embeddings emb
        JOIN chunks c ON c.id = emb.chunk_id
        WHERE c.repo_id = ? AND c.scan_run_id = ?
        """,
        (repo_id, scan_run_id),
    ).fetchone()
    return int(row["total"]) if row is not None else 0


def sync_embeddings_for_scan(
    connection: sqlite3.Connection,
    settings: Settings,
    repo_id: str,
    scan_run_id: str,
) -> VectorSyncStats:
    """为指定 scan 同步 embeddings。"""

    if not settings.vector_index_enabled:
        return VectorSyncStats()

    provider = build_embedding_provider(settings)
    model_fingerprint = build_embedding_fingerprint(provider.provider_name, provider.model_name, provider.revision)
    stats = VectorSyncStats()
    chunk_rows = connection.execute(
        """
        SELECT id, content, content_hash
        FROM chunks
        WHERE repo_id = ? AND scan_run_id = ?
        ORDER BY id
        """,
        (repo_id, scan_run_id),
    ).fetchall()
    if not chunk_rows:
        return stats

    reusable_by_hash = _load_reusable_embeddings(
        connection,
        repo_id,
        [row["content_hash"] for row in chunk_rows],
        model_fingerprint,
        provider.dimension,
    )

    pending_by_hash: dict[str, list[sqlite3.Row]] = defaultdict(list)
    pending_content: dict[str, str] = {}
    for row in chunk_rows:
        blob = reusable_by_hash.get(row["content_hash"])
        if blob is not None:
            upsert_embedding_blob(connection, row["id"], blob, model_fingerprint, provider.dimension)
            stats.reused_embeddings += 1
            continue
        pending_by_hash[row["content_hash"]].append(row)
        pending_content.setdefault(row["content_hash"], row["content"])

    hashes = list(pending_by_hash)
    batch_size = settings.embedding_batch_size
    for start in range(0, len(hashes), batch_size):
        batch_hashes = hashes[start : start + batch_size]
        vectors = provider.embed_documents([pending_content[item] for item in batch_hashes])
        for content_hash, vector in zip(batch_hashes, vectors, strict=True):
            blob = serialize_embedding(vector, provider.dimension)
            for row in pending_by_hash[content_hash]:
                upsert_embedding_blob(connection, row["id"], blob, model_fingerprint, provider.dimension)
                stats.generated_embeddings += 1

    connection.execute(
        """
        UPDATE chunks
        SET embedding_model = ?
        WHERE repo_id = ? AND scan_run_id = ?
        """,
        (model_fingerprint, repo_id, scan_run_id),
    )
    stats.orphan_embeddings_removed = prune_orphan_embeddings(connection)
    return stats


def _load_reusable_embeddings(
    connection: sqlite3.Connection,
    repo_id: str,
    content_hashes: Sequence[str],
    model_fingerprint: str,
    dimension: int,
) -> dict[str, bytes]:
    """按 content_hash 复用历史 embedding。"""

    if not content_hashes:
        return {}
    placeholders = ", ".join("?" for _ in content_hashes)
    rows = connection.execute(
        f"""
        SELECT c.content_hash, emb.embedding
        FROM chunks c
        JOIN embeddings emb ON emb.chunk_id = c.id
        WHERE c.repo_id = ?
          AND c.content_hash IN ({placeholders})
          AND emb.model = ?
          AND emb.dim = ?
        """,
        [repo_id, *content_hashes, model_fingerprint, dimension],
    ).fetchall()

    reusable: dict[str, bytes] = {}
    for row in rows:
        reusable.setdefault(row["content_hash"], row["embedding"])
    return reusable
