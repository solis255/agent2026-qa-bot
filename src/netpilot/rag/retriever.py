"""Validated local knowledge retrieval over a persisted FAISS index."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import faiss
import numpy as np

from netpilot.config import Settings
from netpilot.rag.embeddings import EmbeddingProvider, FastEmbedProvider
from netpilot.rag.errors import RAGError, RAGIndexError
from netpilot.rag.index import load_index
from netpilot.rag.schemas import (
    KnowledgeChunk,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
)


logger = logging.getLogger(__name__)


class Retriever(Protocol):
    def search(self, query: str, top_k: int | None = None) -> list[KnowledgeSearchResult]: ...


class FaissRetriever:
    def __init__(
        self,
        vector_index: object,
        chunks: list[KnowledgeChunk],
        embedder: EmbeddingProvider,
        *,
        top_k: int = 4,
        min_score: float = 0.35,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        self._index = vector_index
        self._chunks = chunks
        self._embedder = embedder
        self._top_k = top_k
        self._min_score = min_score

    @classmethod
    def open(
        cls,
        index_dir: Path,
        embedder: EmbeddingProvider,
        *,
        top_k: int = 4,
        min_score: float = 0.35,
    ) -> "FaissRetriever":
        vector_index, chunks, _manifest = load_index(
            index_dir,
            expected_model=embedder.model_name,
        )
        return cls(
            vector_index,
            chunks,
            embedder,
            top_k=top_k,
            min_score=min_score,
        )

    def search(self, query: str, top_k: int | None = None) -> list[KnowledgeSearchResult]:
        normalized = KnowledgeSearchInput(query=query).query
        limit = self._top_k if top_k is None else top_k
        if not 1 <= limit <= 20:
            raise ValueError("top_k must be between 1 and 20")
        vector = np.asarray([self._embedder.embed_query(normalized)], dtype="float32")
        if vector.ndim != 2 or vector.shape[0] != 1 or vector.shape[1] != self._index.d:
            raise RAGIndexError("查询向量维度与知识索引不一致。")
        if not np.isfinite(vector).all():
            raise RAGIndexError("查询向量包含非有限数值。")
        faiss.normalize_L2(vector)
        scores, positions = self._index.search(vector, min(limit, len(self._chunks)))
        results: list[KnowledgeSearchResult] = []
        for score, position in zip(scores[0], positions[0]):
            numeric_score = float(score)
            if position < 0 or numeric_score < self._min_score:
                continue
            chunk = self._chunks[int(position)]
            results.append(
                KnowledgeSearchResult(
                    **chunk.model_dump(mode="json"),
                    score=max(-1.0, min(1.0, numeric_score)),
                )
            )
        return results


def load_configured_retriever(settings: Settings) -> FaissRetriever | None:
    """Open an existing index without downloading a model during app startup."""

    if not settings.rag_enabled:
        return None
    embedder = FastEmbedProvider(
        settings.embedding_model,
        cache_dir=settings.rag_model_cache_dir,
        local_files_only=True,
    )
    try:
        retriever = FaissRetriever.open(
            settings.rag_index_dir,
            embedder,
            top_k=settings.rag_top_k,
            min_score=settings.rag_min_score,
        )
        embedder.ensure_available()
        return retriever
    except (RAGError, OSError, ValueError):
        logger.info("RAG index is not ready; knowledge_search remains disabled")
        return None
