from contextgraph_studio.domain import ScoredChunk
from contextgraph_studio.retrieval.fusion import weighted_reciprocal_rank_fusion


def make_chunk(chunk_id: str, *, source: str, score: float = 1.0) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        file_path=f"{chunk_id}.py",
        entity_id=None,
        entity=chunk_id,
        entity_type="function",
        category="source_code",
        chunk_kind="symbol",
        line_start=1,
        line_end=10,
        score=score,
        source=source,
        tokens_estimate=50,
    )


def test_weighted_rrf_boosts_shared_hits() -> None:
    bm25 = [make_chunk("a", source="bm25"), make_chunk("b", source="bm25")]
    vector = [make_chunk("b", source="vector"), make_chunk("c", source="vector")]

    fused = weighted_reciprocal_rank_fusion(
        {"bm25": bm25, "vector": vector},
        {"bm25": 0.4, "vector": 0.6},
        k=60,
    )

    assert [item.chunk_id for item in fused][:2] == ["b", "c"]
    assert fused[0].source == "bm25+vector"


def test_weighted_rrf_rejects_invalid_k() -> None:
    try:
        weighted_reciprocal_rank_fusion({}, {}, k=0)
    except ValueError as exc:
        assert "RRF k" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for invalid RRF k")
