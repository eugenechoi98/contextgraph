from pathlib import Path

from contextgraph_studio.config import Settings
from contextgraph_studio.services.indexer import index_repository
from contextgraph_studio.services.retriever import get_trace, retrieve_context


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
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_hybrid_retrieve_uses_bm25_and_graph(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def normalize_token(token: str) -> str:\n"
        "    return token.strip()\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    cleaned = normalize_token(token)\n"
        "    return cleaned == 'ok'\n",
        encoding="utf-8",
    )

    settings = make_settings(tmp_path)
    result = index_repository(repo, settings)
    pack = retrieve_context("verify token auth flow", settings, repo_id=result["repo_id"], top_k=5, max_tokens=500)
    trace = get_trace(pack.trace_id, settings)

    assert "bm25" in pack.retrieval_strategy
    assert "graph" in pack.retrieval_strategy
    assert pack.graph_paths
    assert trace["graph_hits_json"]
    assert any(item.graph_distance > 0 for item in pack.required + pack.supporting)


def test_hybrid_retrieve_uses_vector_when_enabled(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token(token: str) -> bool:\n    return token == 'ok'\n", encoding="utf-8")
    (repo / "session.py").write_text("def issue_session(user_id: str) -> str:\n    return user_id\n", encoding="utf-8")

    settings = make_settings(tmp_path, vector_index_enabled=True, hybrid_vector_enabled=True)
    result = index_repository(repo, settings)
    pack = retrieve_context("verify token", settings, repo_id=result["repo_id"], top_k=5, max_tokens=500)
    trace = get_trace(pack.trace_id, settings)

    assert "vector" in pack.retrieval_strategy
    assert trace["vector_hits_json"]


def test_hybrid_retrieve_degrades_when_vector_unavailable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token(token: str) -> bool:\n    return token == 'ok'\n", encoding="utf-8")

    settings = make_settings(tmp_path, hybrid_vector_enabled=True, vector_index_enabled=False)
    result = index_repository(repo, settings)
    pack = retrieve_context("verify token", settings, repo_id=result["repo_id"], top_k=5, max_tokens=500)

    assert "vector" not in pack.retrieval_strategy
    assert any(note.startswith("Vector recall skipped:") for note in pack.risk_notes)
