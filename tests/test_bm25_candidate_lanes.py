from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.planner import build_plan
from contextgraph_studio.services.retriever import (
    build_lexical_expansion_terms,
    retrieve_context_debug,
    stable_merge_and_dedupe_hits,
)
from contextgraph_studio.domain import ScoredChunk


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
        "vector_index_enabled": False,
        "hybrid_vector_enabled": False,
        "hybrid_graph_enabled": True,
        "embedding_provider": "deterministic",
        "embedding_model": "deterministic-sha256",
        "embedding_dimension": 16,
        "embedding_batch_size": 8,
        "bm25_general_candidate_limit": 6,
        "bm25_source_code_candidate_limit": 4,
        "bm25_source_code_lane_enabled": True,
        "bm25_lexical_expansion_enabled": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _chunk(chunk_id: str, file_path: str, source: str) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        entity_id=chunk_id,
        entity=file_path,
        entity_type="function",
        category="source_code",
        chunk_kind="symbol",
        line_start=1,
        line_end=2,
        score=1.0,
        source=source,
        tokens_estimate=10,
        graph_distance=0,
        reason=source,
        content=file_path,
    )


def build_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "notes.md").write_text(
        "# Structure-aware Chunking\n\nMarkdown sections and symbols overview.\n",
        encoding="utf-8",
    )
    (repo / "chunker.py").write_text(
        "def chunk_markdown(text: str) -> list[str]:\n"
        "    return [text]\n\n"
        "def chunk_source_file(text: str) -> list[str]:\n"
        "    return chunk_markdown(text)\n",
        encoding="utf-8",
    )
    (repo / "parser.py").write_text(
        "def parse_symbols(source: str) -> list[str]:\n"
        "    return source.split()\n",
        encoding="utf-8",
    )


def test_lexical_expansion_is_stable_and_code_oriented() -> None:
    terms = build_lexical_expansion_terms("structure-aware chunking for Python symbols")

    assert terms == build_lexical_expansion_terms("structure-aware chunking for Python symbols")
    assert "structure" in terms
    assert "aware" in terms
    assert "chunking" in terms
    assert "chunk" in terms
    assert "chunker" in terms
    assert "contextgraph_studio/services/chunker.py" not in terms
    assert "" not in terms


def test_lexical_expansion_handles_empty_query() -> None:
    assert build_lexical_expansion_terms("   ") == []


def test_stable_merge_preserves_general_order_and_dedupes() -> None:
    general = [_chunk("a", "docs.md", "bm25"), _chunk("b", "api.py", "bm25")]
    source = [_chunk("b", "api.py", "bm25_source_code"), _chunk("c", "chunker.py", "bm25_source_code")]

    merged = stable_merge_and_dedupe_hits(general, source, limit=3)

    assert [item.chunk_id for item in merged] == ["a", "b", "c"]
    assert merged[0].source == "bm25"


def test_plan_disables_source_code_lane_for_documentation_query(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    plan = build_plan("update deploy config docs", settings, task_hint="general")

    assert plan.source_code_lane_enabled is False


def test_retrieve_context_debug_exposes_bm25_lane_diagnostics(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    _, debug = retrieve_context_debug(
        "structure-aware chunking for markdown symbols",
        settings,
        repo_id=indexed["repo_id"],
        top_k=8,
        task_hint="general",
    )

    lanes = debug["route_diagnostics"]["bm25_lanes"]
    assert lanes["source_code_lane_enabled"] is True
    assert lanes["general_limit"] == settings.bm25_general_candidate_limit
    assert lanes["source_code_limit"] == settings.bm25_source_code_candidate_limit
    assert lanes["source_code_hit_count"] >= 1


def test_retrieve_context_debug_keeps_doc_queries_off_source_code_lane(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    build_repo(repo)
    settings = make_settings(tmp_path)
    indexed = index_repository(repo, settings)

    _, debug = retrieve_context_debug(
        "deployment config documentation",
        settings,
        repo_id=indexed["repo_id"],
        top_k=8,
        task_hint="configuration",
    )

    lanes = debug["route_diagnostics"]["bm25_lanes"]
    assert lanes["source_code_lane_enabled"] is False
