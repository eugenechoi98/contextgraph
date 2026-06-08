from pathlib import Path

import pytest

from contextgraph_studio.config import Settings
from contextgraph_studio.indexing.embedder import (
    EmbeddingProviderError,
    SentenceTransformerEmbeddingProvider,
    build_embedding_provider,
)


def make_settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "data_dir": tmp_path / ".data",
        "database_path": tmp_path / ".data" / "contextgraph.db",
        "embedding_provider": "sentence-transformer",
        "embedding_model": "nomic-ai/nomic-embed-code",
        "embedding_dimension": 768,
        "embedding_batch_size": 4,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_sentence_transformer_defaults_to_no_download(tmp_path: Path) -> None:
    provider = build_embedding_provider(make_settings(tmp_path))

    assert isinstance(provider, SentenceTransformerEmbeddingProvider)
    assert provider.model_name == "nomic-ai/nomic-embed-code"
    assert provider.dimension == 768
    assert provider._local_files_only is True  # type: ignore[attr-defined]
    assert provider._cache_dir is None  # type: ignore[attr-defined]
    assert provider._trust_remote_code is False  # type: ignore[attr-defined]


def test_sentence_transformer_missing_dependency_error_is_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        batch_size=4,
        local_files_only=True,
    )

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "sentence_transformers":
            raise ImportError("missing for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed_documents(["def alpha(): pass"])

    assert "sentence-transformers is not installed" in str(exc_info.value)


def test_sentence_transformer_can_opt_in_to_downloadable_mode(tmp_path: Path) -> None:
    provider = build_embedding_provider(
        make_settings(
            tmp_path,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dimension=384,
            embedding_cache_dir=tmp_path / "cache",
            embedding_local_files_only=False,
            embedding_device="cpu",
        )
    )

    assert isinstance(provider, SentenceTransformerEmbeddingProvider)
    assert provider._local_files_only is False  # type: ignore[attr-defined]
    assert provider._cache_dir == str(tmp_path / "cache")  # type: ignore[attr-defined]
    assert provider._device == "cpu"  # type: ignore[attr-defined]


def test_coderankembed_requires_explicit_trust_remote_code() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model_name="nomic-ai/CodeRankEmbed",
        dimension=768,
        batch_size=4,
        local_files_only=True,
        trust_remote_code=False,
    )

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed_queries(["chunking query"])

    assert "requires trust_remote_code=True" in str(exc_info.value)


def test_coderankembed_uses_pinned_profile_revision_when_not_overridden(tmp_path: Path) -> None:
    provider = build_embedding_provider(
        make_settings(
            tmp_path,
            embedding_model="nomic-ai/CodeRankEmbed",
            embedding_trust_remote_code=True,
        )
    )

    assert isinstance(provider, SentenceTransformerEmbeddingProvider)
    assert provider.revision == "3c4b60807d71f79b43f3c4363786d9493691f8b1"
