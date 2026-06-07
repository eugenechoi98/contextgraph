"""Embedding provider 抽象与实现。"""

from __future__ import annotations

import hashlib
from math import sqrt
from typing import Protocol

import numpy as np

from contextgraph_studio.config import Settings


class EmbeddingProviderError(RuntimeError):
    """Embedding provider 相关错误。"""


class EmbeddingProvider(Protocol):
    """统一 embedding provider 协议。"""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


def validate_embedding_output(
    texts: list[str],
    vectors: list[list[float]],
    expected_dimension: int,
) -> list[list[float]]:
    """校验 provider 输出数量与维度。"""

    if expected_dimension <= 0:
        raise EmbeddingProviderError(f"Embedding dimension must be positive, got {expected_dimension}.")
    if len(vectors) != len(texts):
        raise EmbeddingProviderError(
            "Embedding provider returned a different number of vectors than input texts."
        )

    normalized: list[list[float]] = []
    for index, vector in enumerate(vectors):
        array = np.asarray(vector, dtype=np.float32)
        if array.ndim != 1:
            raise EmbeddingProviderError(f"Embedding at index {index} must be one-dimensional.")
        if array.shape[0] != expected_dimension:
            raise EmbeddingProviderError(
                f"Embedding at index {index} has dimension {array.shape[0]}, expected {expected_dimension}."
            )
        normalized.append(array.astype(np.float32, copy=False).tolist())
    return normalized


class DeterministicEmbeddingProvider:
    """仅用于测试与离线开发的稳定 embedding provider。"""

    def __init__(self, dimension: int, model_name: str = "deterministic-sha256") -> None:
        if dimension <= 0:
            raise EmbeddingProviderError(f"Embedding dimension must be positive, got {dimension}.")
        self._dimension = dimension
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "deterministic"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [self._embed_one(text) for text in texts]
        return validate_embedding_output(texts, vectors, self.dimension)

    def _embed_one(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * self.dimension

        values: list[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < self.dimension:
            digest = hashlib.sha256(seed + b"::" + str(counter).encode("ascii")).digest()
            counter += 1
            for start in range(0, len(digest), 4):
                chunk = digest[start : start + 4]
                raw = int.from_bytes(chunk, byteorder="big", signed=False)
                scaled = (raw / 4_294_967_295.0) * 2.0 - 1.0
                values.append(float(scaled))
                if len(values) == self.dimension:
                    break

        norm = sqrt(sum(value * value for value in values))
        if norm > 0:
            values = [value / norm for value in values]
        return values


class SentenceTransformerEmbeddingProvider:
    """延迟加载 sentence-transformers 的本地模型适配器。"""

    def __init__(
        self,
        model_name: str,
        dimension: int,
        batch_size: int,
    ) -> None:
        if dimension <= 0:
            raise EmbeddingProviderError(f"Embedding dimension must be positive, got {dimension}.")
        if batch_size <= 0:
            raise EmbeddingProviderError(f"Embedding batch size must be positive, got {batch_size}.")
        self._model_name = model_name
        self._dimension = dimension
        self._batch_size = batch_size
        self._model = None

    @property
    def provider_name(self) -> str:
        return "sentence-transformer"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not all(isinstance(text, str) for text in texts):
            raise EmbeddingProviderError("Embedding inputs must all be strings.")

        clean_texts = [text if text.strip() else " " for text in texts]
        try:
            model = self._get_model()
            matrix = model.encode(
                clean_texts,
                batch_size=self._batch_size,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:  # pragma: no cover - 依赖与模型环境相关
            raise EmbeddingProviderError(
                f"Failed to load or run local embedding model '{self.model_name}'. "
                "Install the optional local embeddings extra and ensure the model is available."
            ) from exc

        vectors = np.asarray(matrix, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        return validate_embedding_output(
            texts,
            [row.tolist() for row in vectors],
            self.dimension,
        )

    def _get_model(self):  # pragma: no cover - 依赖与模型环境相关
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderError(
                "sentence-transformers is not installed. "
                "Install with `pip install -e .[local-embeddings]` to enable local embedding models."
            ) from exc
        self._model = SentenceTransformer(self.model_name, trust_remote_code=True)
        return self._model


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """按配置创建 embedding provider。"""

    provider_name = settings.embedding_provider.strip().lower()
    if provider_name == "deterministic":
        return DeterministicEmbeddingProvider(
            dimension=settings.embedding_dimension,
            model_name=settings.embedding_model,
        )
    if provider_name in {"sentence_transformer", "sentence-transformer", "local_nomic", "nomic"}:
        return SentenceTransformerEmbeddingProvider(
            model_name=settings.embedding_model,
            dimension=settings.embedding_dimension,
            batch_size=settings.embedding_batch_size,
        )
    raise EmbeddingProviderError(
        f"Unsupported embedding provider '{settings.embedding_provider}'. "
        "Use 'deterministic' or 'sentence_transformer'."
    )
