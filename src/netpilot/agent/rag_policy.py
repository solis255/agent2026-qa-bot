"""Bounded, deterministic RAG-query deduplication for one Agent turn."""

from __future__ import annotations

import re
import unicodedata


_ASCII_TOKEN = re.compile(r"[a-z0-9]+")
_HAN_CHARACTER = re.compile(r"[\u3400-\u9fff]")


def normalize_rag_query(query: str) -> str:
    """Normalize harmless formatting differences without rewriting meaning."""

    normalized = unicodedata.normalize("NFKC", query).casefold()
    tokens = _ASCII_TOKEN.findall(normalized)
    han = _HAN_CHARACTER.findall(normalized)
    return " ".join([*han, *tokens])


def rag_query_similarity(left: str, right: str) -> float:
    """Return Jaccard similarity over normalized Chinese chars and words."""

    left_tokens = set(normalize_rag_query(left).split())
    right_tokens = set(normalize_rag_query(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def find_duplicate_rag_query(
    query: str,
    previous_queries: list[str],
    *,
    threshold: float = 0.55,
) -> str | None:
    """Find an exact or near-synonymous query that should be reused."""

    normalized = normalize_rag_query(query)
    for previous in previous_queries:
        if normalized == normalize_rag_query(previous):
            return previous
        if rag_query_similarity(query, previous) >= threshold:
            return previous
    return None
