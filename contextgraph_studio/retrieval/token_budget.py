"""Token budget packing for Context Packs."""

from __future__ import annotations

from dataclasses import dataclass

from contextgraph_studio.domain import ScoredChunk


@dataclass(slots=True)
class FilteredChunk:
    """A candidate filtered out during packing."""

    chunk_id: str
    file_path: str
    source: str
    reason: str
    score: float
    tokens_estimate: int


@dataclass(slots=True)
class PackedSelection:
    """Packed retrieval result under a token budget."""

    required: list[ScoredChunk]
    supporting: list[ScoredChunk]
    filtered_out: list[FilteredChunk]
    token_estimate: int


def pack_chunks(
    candidates: list[ScoredChunk],
    *,
    token_budget: int,
    required_chunk_limit: int,
    priority_categories: list[str],
    priority_entity_types: list[str],
) -> PackedSelection:
    """Pack ranked chunks into required and supporting buckets under budget."""

    if token_budget <= 0:
        raise ValueError("token_budget must be greater than 0.")
    if required_chunk_limit <= 0:
        raise ValueError("required_chunk_limit must be greater than 0.")

    ordered = sorted(
        candidates,
        key=lambda item: (
            -_required_priority(item),
            -_domain_priority(item, priority_categories, priority_entity_types),
            -item.score,
            item.graph_distance,
            item.file_path,
            item.chunk_id,
        ),
    )

    required: list[ScoredChunk] = []
    supporting: list[ScoredChunk] = []
    filtered_out: list[FilteredChunk] = []
    total_tokens = 0

    for chunk in ordered:
        token_cost = max(int(chunk.tokens_estimate), 0)
        if total_tokens + token_cost > token_budget:
            filtered_out.append(_filtered(chunk, "token_budget_exceeded"))
            continue

        if len(required) < required_chunk_limit and _required_priority(chunk) > 0:
            required.append(chunk)
            total_tokens += token_cost
            continue

        supporting.append(chunk)
        total_tokens += token_cost

    return PackedSelection(
        required=required,
        supporting=supporting,
        filtered_out=filtered_out,
        token_estimate=total_tokens,
    )


def _required_priority(chunk: ScoredChunk) -> int:
    if "bm25" in chunk.source or "vector" in chunk.source:
        return 2
    if chunk.graph_distance == 0:
        return 1
    return 0


def _domain_priority(
    chunk: ScoredChunk,
    priority_categories: list[str],
    priority_entity_types: list[str],
) -> int:
    score = 0
    if chunk.category and chunk.category in priority_categories:
        score += 2
    if chunk.entity_type and chunk.entity_type in priority_entity_types:
        score += 1
    return score


def _filtered(chunk: ScoredChunk, reason: str) -> FilteredChunk:
    return FilteredChunk(
        chunk_id=chunk.chunk_id,
        file_path=chunk.file_path,
        source=chunk.source,
        reason=reason,
        score=chunk.score,
        tokens_estimate=chunk.tokens_estimate,
    )
