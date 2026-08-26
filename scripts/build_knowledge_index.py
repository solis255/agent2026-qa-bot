#!/usr/bin/env python3
"""Build the local NetPilot FAISS index from source-preserving documents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from netpilot.config import PROJECT_ROOT, Settings
from netpilot.rag import (
    FastEmbedProvider,
    RAGError,
    build_index,
    chunk_documents,
    load_documents,
)


def _configure_windows_console() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建 NetPilot 本地知识索引")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=PROJECT_ROOT / "knowledge" / "raw",
        help="带来源元数据的 Markdown/TXT 目录",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=None,
        help="索引输出目录；默认使用 RAG_INDEX_DIR",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="只使用已经缓存的 Embedding 模型",
    )
    return parser.parse_args()


def main() -> int:
    _configure_windows_console()
    args = parse_args()
    try:
        settings = Settings()
        documents = load_documents(args.raw_dir)
        chunks = chunk_documents(
            documents,
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        )
        embedder = FastEmbedProvider(
            settings.embedding_model,
            cache_dir=settings.rag_model_cache_dir,
            local_files_only=args.offline,
        )
        manifest = build_index(
            chunks,
            embedder,
            args.index_dir or settings.rag_index_dir,
            document_count=len(documents),
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
        )
    except (RAGError, ValidationError, ValueError) as exc:
        print(f"知识索引构建失败：{exc}")
        return 1

    print(
        f"知识索引构建完成：{manifest.document_count} 个文档，"
        f"{manifest.chunk_count} 个知识块，维度 {manifest.dimension}。"
    )
    print(f"Embedding：{manifest.embedding_model}")
    print(f"输出目录：{(args.index_dir or settings.rag_index_dir).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
