"""独立向量检索入口。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.indexing.embedder import build_embedding_provider
from contextgraph_studio.indexing.vector_store import (
    build_embedding_fingerprint,
    count_embeddings_for_scan,
    deserialize_embedding,
    list_embeddings_for_scan,
    split_embedding_fingerprint,
)
from contextgraph_studio.services.scan_resolver import resolve_repo_and_scan_run


@dataclass(slots=True)
class VectorSearchResult:
    """向量检索结果。"""

    chunk_id: str
    file_path: str
    entity_id: str | None
    entity: str | None
    entity_type: str | None
    category: str | None
    chunk_kind: str
    line_start: int | None
    line_end: int | None
    score: float
    tokens_estimate: int
    content: str | None
    provider: str
    model: str
    dim: int


def cosine_similarity(query_vector: np.ndarray, candidate_vector: np.ndarray) -> float:
    """计算余弦相似度，零向量显式返回 0。"""

    query_norm = float(np.linalg.norm(query_vector))
    candidate_norm = float(np.linalg.norm(candidate_vector))
    if query_norm == 0.0 or candidate_norm == 0.0:
        return 0.0
    return float(np.dot(query_vector, candidate_vector) / (query_norm * candidate_norm))


def search_similar_chunks(
    query: str,
    settings: Settings,
    repo_id: str | None = None,
    top_k: int = 10,
) -> list[VectorSearchResult]:
    """执行独立的 vector search。"""

    if top_k <= 0:
        raise ValueError("top_k must be greater than 0 for vector search.")
    if not query.strip():
        raise ValueError("Vector search query must not be empty.")
    if not settings.vector_index_enabled:
        raise RuntimeError("Vector index is disabled. Set VECTOR_INDEX_ENABLED=true and re-run indexing.")

    init_db(settings)
    provider = build_embedding_provider(settings)
    query_vector = np.asarray(provider.embed_queries([query])[0], dtype=np.float32)
    model_fingerprint = build_embedding_fingerprint(provider.provider_name, provider.model_name, provider.revision)

    with connect(settings.database_path) as connection:
        resolved_repo_id, scan_run_id = resolve_repo_and_scan_run(connection, repo_id)
        rows = list_embeddings_for_scan(
            connection,
            resolved_repo_id,
            scan_run_id,
            model_fingerprint,
            provider.dimension,
        )
        if not rows:
            total_embeddings = count_embeddings_for_scan(connection, resolved_repo_id, scan_run_id)
            if total_embeddings > 0:
                raise RuntimeError(
                    "Latest successful scan has embeddings, but not for the configured provider/model/dimension. "
                    "Re-run `cgstudio index` with the current embedding settings."
                )
            return []

    results: list[VectorSearchResult] = []
    for row in rows:
        candidate_vector = deserialize_embedding(row["embedding"], int(row["dim"]))
        provider_name, model_name = split_embedding_fingerprint(row["model"])
        results.append(
            VectorSearchResult(
                chunk_id=row["chunk_id"],
                file_path=row["file_path"],
                entity_id=row["entity_id"],
                entity=row["entity"],
                entity_type=row["entity_type"],
                category=row["category"],
                chunk_kind=row["chunk_kind"],
                line_start=row["line_start"],
                line_end=row["line_end"],
                score=cosine_similarity(query_vector, candidate_vector),
                tokens_estimate=int(row["tokens_estimate"]),
                content=row["content"],
                provider=provider_name,
                model=model_name,
                dim=int(row["dim"]),
            )
        )

    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]
