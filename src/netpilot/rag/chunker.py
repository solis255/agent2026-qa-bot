"""Deterministic Chinese-friendly character chunking."""

from __future__ import annotations

import hashlib

from netpilot.rag.schemas import KnowledgeChunk, KnowledgeDocument


BOUNDARIES = ("\n\n", "。\n", "。", "！", "？", "\n")


def chunk_documents(
    documents: list[KnowledgeDocument],
    *,
    chunk_size: int,
    overlap: int,
) -> list[KnowledgeChunk]:
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk overlap must be non-negative and smaller than size")

    chunks: list[KnowledgeChunk] = []
    for document in documents:
        chunks.extend(_chunk_document(document, chunk_size, overlap))
    return chunks


def _chunk_document(
    document: KnowledgeDocument,
    chunk_size: int,
    overlap: int,
) -> list[KnowledgeChunk]:
    text = "\n".join(line.rstrip() for line in document.content.splitlines()).strip()
    chunks: list[KnowledgeChunk] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + chunk_size)
        end = hard_end
        if hard_end < len(text):
            minimum = start + chunk_size // 2
            candidates = [
                text.rfind(boundary, minimum, hard_end)
                for boundary in BOUNDARIES
            ]
            boundary = max(candidates)
            if boundary >= minimum:
                end = boundary + 1
        content = text[start:end].strip()
        if content:
            digest = hashlib.sha256(
                f"{document.file}\0{start}\0{content}".encode("utf-8")
            ).hexdigest()[:24]
            chunks.append(
                KnowledgeChunk(
                    chunk_id=digest,
                    title=document.title,
                    source=document.source,
                    source_type=document.source_type,
                    file=document.file,
                    content=content,
                )
            )
        if end >= len(text):
            break
        next_start = max(0, end - overlap)
        start = next_start if next_start > start else end
    return chunks
