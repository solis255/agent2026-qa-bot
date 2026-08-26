"""Configurable production and deterministic test embedding providers."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from netpilot.rag.errors import RAGEmbeddingError


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider:
    """Lazy ONNX-backed BGE embeddings with explicit offline startup mode."""

    def __init__(
        self,
        model_name: str,
        *,
        cache_dir: Path,
        local_files_only: bool,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._local_files_only = local_files_only
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return [vector.tolist() for vector in self._load().passage_embed(list(texts))]
        except Exception as exc:
            raise RAGEmbeddingError("知识文档 Embedding 生成失败。") from exc

    def embed_query(self, text: str) -> list[float]:
        try:
            vectors = list(self._load().query_embed([text]))
        except Exception as exc:
            raise RAGEmbeddingError("知识查询 Embedding 生成失败。") from exc
        if len(vectors) != 1:
            raise RAGEmbeddingError("知识查询 Embedding 返回数量异常。")
        return vectors[0].tolist()

    def ensure_available(self) -> None:
        """Load the model using the configured online/offline policy."""

        self._load()

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding

            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self._cache_dir),
                local_files_only=self._local_files_only,
            )
        except Exception as exc:
            mode = "本地缓存" if self._local_files_only else "模型仓库"
            raise RAGEmbeddingError(f"无法从{mode}加载 Embedding 模型。") from exc
        return self._model


class DeterministicHashEmbedding:
    """Small dependency-free semantic-ish embedding reserved for tests."""

    def __init__(self, dimension: int = 96) -> None:
        if dimension < 8:
            raise ValueError("dimension must be at least 8")
        self.dimension = dimension

    @property
    def model_name(self) -> str:
        return f"test/hash-embedding-{self.dimension}"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        normalized = "".join(text.lower().split())
        tokens = list(normalized)
        tokens.extend(normalized[index : index + 2] for index in range(len(normalized) - 1))
        vector = [0.0] * self.dimension
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
