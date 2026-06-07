from contextgraph_studio.domain import ScoredChunk
from contextgraph_studio.retrieval.token_budget import pack_chunks


def make_chunk(
    chunk_id: str,
    *,
    source: str,
    score: float,
    tokens_estimate: int,
    category: str = "source_code",
    entity_type: str = "function",
    graph_distance: int = 0,
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        file_path=f"{chunk_id}.py",
        entity_id=chunk_id,
        entity=chunk_id,
        entity_type=entity_type,
        category=category,
        chunk_kind="symbol",
        line_start=1,
        line_end=20,
        score=score,
        source=source,
        tokens_estimate=tokens_estimate,
        graph_distance=graph_distance,
    )


def test_pack_chunks_prioritizes_direct_hits_and_respects_budget() -> None:
    packed = pack_chunks(
        [
            make_chunk("graph_neighbor", source="graph", score=0.9, tokens_estimate=60, graph_distance=1),
            make_chunk("direct_bm25", source="bm25", score=0.4, tokens_estimate=40),
            make_chunk("direct_vector", source="vector", score=0.5, tokens_estimate=40),
            make_chunk("too_large", source="bm25", score=0.3, tokens_estimate=80),
        ],
        token_budget=140,
        required_chunk_limit=2,
        priority_categories=["source_code"],
        priority_entity_types=["function"],
    )

    assert [item.chunk_id for item in packed.required] == ["direct_vector", "direct_bm25"]
    assert [item.chunk_id for item in packed.supporting] == ["graph_neighbor"]
    assert packed.filtered_out[0].chunk_id == "too_large"
    assert packed.filtered_out[0].reason == "token_budget_exceeded"
    assert packed.token_estimate == 140


def test_pack_chunks_rejects_invalid_budget() -> None:
    try:
        pack_chunks([], token_budget=0, required_chunk_limit=1, priority_categories=[], priority_entity_types=[])
    except ValueError as exc:
        assert "token_budget" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for invalid token budget")
