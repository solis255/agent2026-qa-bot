"""Safe RAG errors used across indexing and retrieval boundaries."""


class RAGError(RuntimeError):
    """Base error for knowledge loading, indexing, and retrieval."""


class RAGBuildError(RAGError):
    """Raised when trusted source data cannot produce a valid index."""


class RAGIndexError(RAGError):
    """Raised when a persisted index is missing, incompatible, or corrupt."""


class RAGEmbeddingError(RAGError):
    """Raised when an embedding model cannot produce usable vectors."""
