"""Build and load a persistent cosine-similarity FAISS knowledge index."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import faiss
import numpy as np
from pydantic import TypeAdapter, ValidationError

from netpilot.rag.embeddings import EmbeddingProvider
from netpilot.rag.errors import RAGBuildError, RAGIndexError
from netpilot.rag.schemas import IndexManifest, KnowledgeChunk


INDEX_FILE = "vectors.faiss"
CHUNKS_FILE = "chunks.json"
MANIFEST_FILE = "manifest.json"
CHUNK_LIST = TypeAdapter(list[KnowledgeChunk])


def build_index(
    chunks: list[KnowledgeChunk],
    embedder: EmbeddingProvider,
    index_dir: Path,
    *,
    document_count: int,
    chunk_size: int,
    chunk_overlap: int,
) -> IndexManifest:
    if not chunks:
        raise RAGBuildError("没有可写入索引的知识块。")
    try:
        matrix = np.asarray(
            embedder.embed_documents([chunk.content for chunk in chunks]),
            dtype="float32",
        )
    except Exception as exc:
        if isinstance(exc, RAGBuildError):
            raise
        raise RAGBuildError("无法生成知识文档向量。") from exc
    if matrix.ndim != 2 or matrix.shape[0] != len(chunks) or matrix.shape[1] < 1:
        raise RAGBuildError("Embedding 返回了不一致的向量形状。")
    if not np.isfinite(matrix).all():
        raise RAGBuildError("Embedding 包含非有限数值。")

    faiss.normalize_L2(matrix)
    vector_index = faiss.IndexFlatIP(matrix.shape[1])
    vector_index.add(matrix)
    manifest = IndexManifest(
        embedding_model=embedder.model_name,
        dimension=matrix.shape[1],
        document_count=document_count,
        chunk_count=len(chunks),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        built_at=datetime.now(timezone.utc),
        source_files=sorted({chunk.file for chunk in chunks}),
    )
    _persist(index_dir, vector_index, chunks, manifest)
    return manifest


def load_index(
    index_dir: Path,
    *,
    expected_model: str,
) -> tuple[object, list[KnowledgeChunk], IndexManifest]:
    root = index_dir.resolve()
    paths = {
        "index": root / INDEX_FILE,
        "chunks": root / CHUNKS_FILE,
        "manifest": root / MANIFEST_FILE,
    }
    if any(not path.is_file() for path in paths.values()):
        raise RAGIndexError("知识索引不存在或不完整。")
    try:
        manifest = IndexManifest.model_validate_json(
            paths["manifest"].read_text(encoding="utf-8")
        )
        chunks = CHUNK_LIST.validate_json(paths["chunks"].read_text(encoding="utf-8"))
        vector_index = faiss.read_index(str(paths["index"]))
    except (OSError, RuntimeError, ValueError, ValidationError) as exc:
        raise RAGIndexError("知识索引无法解析或已经损坏。") from exc
    if manifest.schema_version != 1:
        raise RAGIndexError("知识索引版本不受支持。")
    if manifest.embedding_model != expected_model:
        raise RAGIndexError("知识索引与当前 Embedding 模型不匹配。")
    if len(chunks) != manifest.chunk_count or vector_index.ntotal != len(chunks):
        raise RAGIndexError("知识索引向量与元数据数量不一致。")
    if vector_index.d != manifest.dimension:
        raise RAGIndexError("知识索引向量维度与 manifest 不一致。")
    return vector_index, chunks, manifest


def _persist(
    index_dir: Path,
    vector_index: object,
    chunks: list[KnowledgeChunk],
    manifest: IndexManifest,
) -> None:
    root = index_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    suffix = uuid4().hex
    temporary = {
        INDEX_FILE: root / f".{INDEX_FILE}.{suffix}.tmp",
        CHUNKS_FILE: root / f".{CHUNKS_FILE}.{suffix}.tmp",
        MANIFEST_FILE: root / f".{MANIFEST_FILE}.{suffix}.tmp",
    }
    try:
        faiss.write_index(vector_index, str(temporary[INDEX_FILE]))
        temporary[CHUNKS_FILE].write_text(
            json.dumps(
                [chunk.model_dump(mode="json") for chunk in chunks],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary[MANIFEST_FILE].write_text(
            json.dumps(manifest.to_json_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary[INDEX_FILE], root / INDEX_FILE)
        os.replace(temporary[CHUNKS_FILE], root / CHUNKS_FILE)
        os.replace(temporary[MANIFEST_FILE], root / MANIFEST_FILE)
    except (OSError, RuntimeError) as exc:
        raise RAGBuildError("知识索引写入失败。") from exc
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)
