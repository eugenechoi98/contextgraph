from pathlib import Path

import pytest

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect
from contextgraph_studio.indexing.embedder import DeterministicEmbeddingProvider
from contextgraph_studio.indexing import vector_store
from contextgraph_studio.retrieval.vector import search_similar_chunks
from contextgraph_studio.services.indexer import index_repository


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
        "vector_index_enabled": True,
        "embedding_provider": "deterministic",
        "embedding_model": "deterministic-sha256",
        "embedding_dimension": 16,
        "embedding_batch_size": 8,
    }
    defaults.update(overrides)
    return Settings(**defaults)


class CountingProvider(DeterministicEmbeddingProvider):
    def __init__(self, dimension: int, model_name: str = "deterministic-sha256") -> None:
        super().__init__(dimension=dimension, model_name=model_name)
        self.total_texts = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.total_texts += len(texts)
        return super().embed_texts(texts)

    def reset(self) -> None:
        self.total_texts = 0


def test_vector_index_writes_embeddings_and_searches(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text(
        "def verify_token(token: str) -> bool:\n    return token == 'ok'\n",
        encoding="utf-8",
    )
    (repo / "session.py").write_text(
        "def issue_session(user_id: str) -> str:\n    return user_id\n",
        encoding="utf-8",
    )

    settings = make_settings(tmp_path)
    result = index_repository(repo, settings)

    with connect(settings.database_path) as connection:
        chunk_total = connection.execute(
            "SELECT COUNT(*) AS total FROM chunks WHERE scan_run_id = ?",
            (result["scan_run_id"],),
        ).fetchone()["total"]
        embedding_total = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM embeddings emb
            JOIN chunks c ON c.id = emb.chunk_id
            WHERE c.scan_run_id = ?
            """,
            (result["scan_run_id"],),
        ).fetchone()["total"]
        model_row = connection.execute(
            """
            SELECT DISTINCT embedding_model
            FROM chunks
            WHERE scan_run_id = ? AND embedding_model IS NOT NULL
            """,
            (result["scan_run_id"],),
        ).fetchone()
    assert embedding_total == chunk_total
    assert model_row["embedding_model"] == "deterministic::deterministic-sha256"

    hits = search_similar_chunks("verify token", settings, repo_id=result["repo_id"], top_k=5)
    assert hits
    assert hits[0].score >= hits[-1].score
    assert hits[0].provider == "deterministic"
    assert hits[0].model == "deterministic-sha256"


def test_vector_index_reuses_unchanged_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token():\n    return True\n", encoding="utf-8")

    provider = CountingProvider(dimension=16)
    monkeypatch.setattr(vector_store, "build_embedding_provider", lambda settings: provider)
    settings = make_settings(tmp_path)

    index_repository(repo, settings)
    assert provider.total_texts > 0

    provider.reset()
    index_repository(repo, settings)
    assert provider.total_texts == 0


def test_vector_index_updates_only_changed_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "auth.py"
    target.write_text(
        "def alpha():\n    return 'a'\n\n\ndef beta():\n    return 'b'\n",
        encoding="utf-8",
    )

    provider = CountingProvider(dimension=16)
    monkeypatch.setattr(vector_store, "build_embedding_provider", lambda settings: provider)
    settings = make_settings(tmp_path)

    index_repository(repo, settings)
    provider.reset()

    target.write_text(
        "def alpha():\n    return 'updated'\n\n\ndef beta():\n    return 'b'\n",
        encoding="utf-8",
    )
    second = index_repository(repo, settings)
    assert 0 < provider.total_texts < int(second["chunk_count"])


def test_vector_index_rebuilds_when_dimension_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "auth.py").write_text("def verify_token():\n    return True\n", encoding="utf-8")

    first_settings = make_settings(tmp_path, embedding_dimension=8)
    index_repository(repo, first_settings)

    provider = CountingProvider(dimension=12)
    monkeypatch.setattr(vector_store, "build_embedding_provider", lambda settings: provider)
    second_settings = make_settings(tmp_path, embedding_dimension=12)
    second = index_repository(repo, second_settings)
    assert provider.total_texts == int(second["chunk_count"])


def test_deleted_file_disappears_from_latest_vector_search(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "auth.py"
    target.write_text("def verify_token():\n    return True\n", encoding="utf-8")
    (repo / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

    settings = make_settings(tmp_path)
    first = index_repository(repo, settings)
    assert search_similar_chunks("verify token", settings, repo_id=first["repo_id"], top_k=5)

    target.unlink()
    second = index_repository(repo, settings)
    hits = search_similar_chunks("verify token", settings, repo_id=second["repo_id"], top_k=5)
    assert all(hit.file_path != "auth.py" for hit in hits)


def test_vector_search_rejects_invalid_inputs_and_disabled_mode(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with pytest.raises(ValueError):
        search_similar_chunks("verify token", settings, top_k=0)

    disabled_settings = make_settings(tmp_path, vector_index_enabled=False)
    with pytest.raises(RuntimeError):
        search_similar_chunks("verify token", disabled_settings)
