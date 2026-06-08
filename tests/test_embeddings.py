import sqlite3
from pathlib import Path

import numpy as np
import pytest

from contextgraph_studio.config import Settings
from contextgraph_studio.db import connect, init_db
from contextgraph_studio.indexing.embedder import (
    DeterministicEmbeddingProvider,
    EmbeddingProviderError,
    SentenceTransformerEmbeddingProvider,
    build_embedding_provider,
    validate_embedding_output,
)
from contextgraph_studio.indexing.vector_store import (
    delete_embeddings_for_chunks,
    deserialize_embedding,
    prune_orphan_embeddings,
    serialize_embedding,
    upsert_embedding_blob,
)


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
    )


def seed_chunk(settings: Settings) -> None:
    init_db(settings)
    with connect(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO repositories (id, local_path, remote_url, default_branch, created_at, updated_at)
            VALUES ('repo-1', 'C:/repo', NULL, NULL, 1, 1)
            """
        )
        connection.execute(
            """
            INSERT INTO scan_runs (id, repo_id, commit_sha, started_at, finished_at, status, stats_json)
            VALUES ('scan-1', 'repo-1', NULL, 1, 2, 'done', '{}')
            """
        )
        connection.execute(
            """
            INSERT INTO files (
                id, scan_run_id, repo_id, file_path, language, category, size_bytes,
                line_count, content_hash, is_excluded
            ) VALUES ('file-1', 'scan-1', 'repo-1', 'app.py', 'python', 'source_code', 10, 1, 'hash-file', 0)
            """
        )
        connection.execute(
            """
            INSERT INTO chunks (
                id, entity_id, file_id, repo_id, scan_run_id, chunk_kind, content,
                tokens_estimate, line_start, line_end, content_hash, embedding_model, created_at
            ) VALUES ('chunk-1', NULL, 'file-1', 'repo-1', 'scan-1', 'symbol', 'def alpha(): pass', 4, 1, 1, 'hash-chunk', NULL, 1)
            """
        )
        connection.commit()


def test_deterministic_provider_is_stable() -> None:
    provider = DeterministicEmbeddingProvider(dimension=8)
    first = provider.embed_documents(["verify token"])
    second = provider.embed_queries(["verify token"])
    third = provider.embed_documents(["issue session"])
    assert first == second
    assert first != third
    assert len(first[0]) == 8


def test_deterministic_provider_handles_empty_inputs() -> None:
    provider = DeterministicEmbeddingProvider(dimension=4)
    assert provider.embed_documents([]) == []
    assert provider.embed_queries([""])[0] == [0.0, 0.0, 0.0, 0.0]


def test_validate_embedding_output_rejects_count_and_dimension_mismatch() -> None:
    with pytest.raises(EmbeddingProviderError):
        validate_embedding_output(["a"], [], 4)
    with pytest.raises(EmbeddingProviderError):
        validate_embedding_output(["a"], [[0.1, 0.2]], 4)


def test_embedding_blob_round_trip_and_cleanup(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed_chunk(settings)
    blob = serialize_embedding([0.5, -0.5], expected_dim=2)

    with connect(settings.database_path) as connection:
        upsert_embedding_blob(connection, "chunk-1", blob, "deterministic::deterministic-sha256", 2)
        connection.commit()

        row = connection.execute(
            "SELECT embedding, model, dim FROM embeddings WHERE chunk_id = 'chunk-1'"
        ).fetchone()
        assert row is not None
        restored = deserialize_embedding(row["embedding"], expected_dim=2)
        assert restored.dtype == np.float32
        assert restored.tolist() == pytest.approx([0.5, -0.5])
        assert row["model"] == "deterministic::deterministic-sha256"
        assert row["dim"] == 2

        deleted = delete_embeddings_for_chunks(connection, ["chunk-1"])
        assert deleted == 1
        upsert_embedding_blob(connection, "chunk-1", blob, "deterministic::deterministic-sha256", 2)
        connection.commit()

    raw = sqlite3.connect(settings.database_path)
    raw.execute("PRAGMA foreign_keys = OFF")
    raw.execute("DELETE FROM chunks WHERE id = 'chunk-1'")
    raw.commit()
    raw.close()

    with connect(settings.database_path) as connection:
        removed = prune_orphan_embeddings(connection)
        assert removed == 1


def test_embedding_blob_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError):
        serialize_embedding([1.0], expected_dim=2)
    with pytest.raises(ValueError):
        deserialize_embedding(b"\x00", expected_dim=1)


def test_build_embedding_provider_passes_sentence_transformer_options(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / ".data",
        database_path=tmp_path / ".data" / "contextgraph.db",
        embedding_provider="sentence-transformer",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        embedding_dimension=384,
        embedding_batch_size=4,
        embedding_device="cpu",
        embedding_cache_dir=tmp_path / "cache",
        embedding_local_files_only=True,
        embedding_revision="main",
    )

    provider = build_embedding_provider(settings)

    assert isinstance(provider, SentenceTransformerEmbeddingProvider)
    assert provider.model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert provider.dimension == 384


def test_sentence_transformer_provider_uses_query_prompt_and_cache_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, list[str]]] = []
    init_kwargs: dict[str, object] = {}

    class FakeModel:
        prompts = {"query": "query: "}

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((kwargs.get("prompt_name"), list(texts)))
            return np.ones((len(texts), 3), dtype=np.float32)

    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):  # type: ignore[no-untyped-def]
            init_kwargs["model_name"] = model_name
            init_kwargs.update(kwargs)
            self.prompts = {"query": "query: "}

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            return FakeModel().encode(texts, **kwargs)

    import sys
    import types

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    provider = SentenceTransformerEmbeddingProvider(
        model_name="nomic-ai/nomic-embed-code",
        dimension=3,
        batch_size=2,
        device="cpu",
        cache_dir="D:/contextgraph-model-cache",
        local_files_only=True,
        revision="main",
    )

    provider.embed_queries(["query text"])
    provider.embed_documents(["def chunk_markdown(): pass"])

    assert calls == [
        ("query", ["query text"]),
        (None, ["def chunk_markdown(): pass"]),
    ]
    assert init_kwargs["model_name"] == "nomic-ai/nomic-embed-code"
    assert init_kwargs["device"] == "cpu"
    assert init_kwargs["cache_folder"] == "D:/contextgraph-model-cache"
    assert init_kwargs["local_files_only"] is True
    assert init_kwargs["revision"] == "main"


def test_sentence_transformer_provider_skips_query_prompt_when_model_has_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, list[str]]] = []

    class FakeModel:
        prompts = {}

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((kwargs.get("prompt_name"), list(texts)))
            return np.ones((len(texts), 3), dtype=np.float32)

    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):  # type: ignore[no-untyped-def]
            self._model = FakeModel()

        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            return self._model.encode(texts, **kwargs)

        @property
        def prompts(self):  # type: ignore[no-untyped-def]
            return self._model.prompts

    import sys
    import types

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    provider = SentenceTransformerEmbeddingProvider(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimension=3,
        batch_size=2,
    )

    provider.embed_queries(["query text"])

    assert calls == [(None, ["query text"])]
