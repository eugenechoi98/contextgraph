"""Fusion helpers for hybrid retrieval."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from contextgraph_studio.domain import ScoredChunk


def weighted_reciprocal_rank_fusion(
    rankings: Mapping[str, list[ScoredChunk]],
    weights: Mapping[str, float],
    *,
    k: int = 60,
) -> list[ScoredChunk]:
    """Fuse multiple ranked lists with weighted reciprocal rank fusion."""

    if k <= 0:
        raise ValueError("RRF k must be greater than 0.")

    fused_scores: dict[str, float] = {}
    merged_chunks: dict[str, ScoredChunk] = {}
    contributing_sources: dict[str, set[str]] = {}

    for source, chunks in rankings.items():
        if not chunks:
            continue
        weight = float(weights.get(source, 1.0))
        seen_chunk_ids: set[str] = set()
        for rank, chunk in enumerate(chunks, start=1):
            if chunk.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.chunk_id)
            fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + (weight / (k + rank))
            merged_chunks[chunk.chunk_id] = _merge_chunk_metadata(merged_chunks.get(chunk.chunk_id), chunk)
            contributing_sources.setdefault(chunk.chunk_id, set()).add(source)

    fused: list[ScoredChunk] = []
    for chunk_id, score in fused_scores.items():
        base = merged_chunks[chunk_id]
        sources = sorted(contributing_sources.get(chunk_id, []))
        fused.append(
            replace(
                base,
                score=score,
                source="+".join(sources) if len(sources) > 1 else (sources[0] if sources else base.source),
                reason=base.reason or (f"Fused from {', '.join(sources)}" if sources else None),
            )
        )

    return sorted(
        fused,
        key=lambda item: (-item.score, item.graph_distance, item.file_path, item.chunk_id),
    )


def _merge_chunk_metadata(existing: ScoredChunk | None, incoming: ScoredChunk) -> ScoredChunk:
    """Preserve richer route metadata when the same chunk appears in multiple rankings."""

    if existing is None:
        return incoming
    return replace(
        existing,
        score=max(existing.score, incoming.score),
        graph_distance=max(existing.graph_distance, incoming.graph_distance),
        path=existing.path or incoming.path,
        reason=existing.reason or incoming.reason,
        provider=existing.provider or incoming.provider,
        model=existing.model or incoming.model,
    )
