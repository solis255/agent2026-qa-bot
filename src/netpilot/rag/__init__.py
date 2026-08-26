"""Local, source-preserving RAG support for campus network knowledge."""

from netpilot.rag.chunker import chunk_documents
from netpilot.rag.embeddings import (
    DeterministicHashEmbedding,
    EmbeddingProvider,
    FastEmbedProvider,
)
from netpilot.rag.errors import RAGBuildError, RAGEmbeddingError, RAGError, RAGIndexError
from netpilot.rag.index import build_index, load_index
from netpilot.rag.loader import load_documents
from netpilot.rag.retriever import FaissRetriever, Retriever, load_configured_retriever
from netpilot.rag.schemas import (
    IndexManifest,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSearchData,
    KnowledgeSearchInput,
    KnowledgeSearchResult,
    KnowledgeSource,
    SourceType,
)

__all__ = [
    "DeterministicHashEmbedding",
    "EmbeddingProvider",
    "FaissRetriever",
    "FastEmbedProvider",
    "IndexManifest",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeSearchData",
    "KnowledgeSearchInput",
    "KnowledgeSearchResult",
    "KnowledgeSource",
    "RAGBuildError",
    "RAGEmbeddingError",
    "RAGError",
    "RAGIndexError",
    "Retriever",
    "SourceType",
    "build_index",
    "chunk_documents",
    "load_configured_retriever",
    "load_documents",
    "load_index",
]
