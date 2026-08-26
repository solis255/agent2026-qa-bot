"""Load small trusted Markdown and text knowledge collections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from netpilot.rag.errors import RAGBuildError
from netpilot.rag.schemas import KnowledgeDocument


SUPPORTED_SUFFIXES = {".md", ".txt"}
MAX_SOURCE_BYTES = 2_000_000
MAX_DOCUMENTS = 500


def load_documents(raw_dir: Path) -> list[KnowledgeDocument]:
    """Load validated front-matter documents without following symlinks."""

    root = raw_dir.resolve()
    if not root.is_dir():
        raise RAGBuildError(f"知识目录不存在：{root}")

    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not paths:
        raise RAGBuildError("knowledge/raw 中没有可索引的 Markdown 或 TXT 文档。")
    if len(paths) > MAX_DOCUMENTS:
        raise RAGBuildError(f"知识文档数量超过上限 {MAX_DOCUMENTS}。")

    documents: list[KnowledgeDocument] = []
    for path in paths:
        if path.is_symlink():
            raise RAGBuildError(f"知识目录不允许符号链接：{path.name}")
        resolved = path.resolve()
        if root not in resolved.parents:
            raise RAGBuildError(f"知识文档越过了 raw 目录：{path.name}")
        if resolved.stat().st_size > MAX_SOURCE_BYTES:
            raise RAGBuildError(f"知识文档超过 2 MB：{path.name}")
        try:
            raw_text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RAGBuildError(f"无法读取 UTF-8 知识文档：{path.name}") from exc
        metadata, content = _parse_front_matter(raw_text, path.name)
        try:
            documents.append(
                KnowledgeDocument(
                    **metadata,
                    file=resolved.relative_to(root).as_posix(),
                    content=content,
                )
            )
        except ValidationError as exc:
            raise RAGBuildError(f"知识文档元数据不合法：{path.name}") from exc
    return documents


def _parse_front_matter(text: str, file_name: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n").lstrip("\ufeff")
    if not normalized.startswith("---\n"):
        raise RAGBuildError(f"知识文档缺少 YAML front matter：{file_name}")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise RAGBuildError(f"知识文档 front matter 未闭合：{file_name}")
    try:
        metadata = yaml.safe_load(normalized[4:end])
    except yaml.YAMLError as exc:
        raise RAGBuildError(f"知识文档 front matter 不是合法 YAML：{file_name}") from exc
    if not isinstance(metadata, dict):
        raise RAGBuildError(f"知识文档 front matter 必须是对象：{file_name}")
    allowed = {"title", "source", "source_type", "retrieved_at"}
    unknown = set(metadata) - allowed
    if unknown:
        raise RAGBuildError(f"知识文档包含未知元数据字段：{file_name}")
    content = normalized[end + 5 :].strip()
    if not content:
        raise RAGBuildError(f"知识文档内容为空：{file_name}")
    return metadata, content
