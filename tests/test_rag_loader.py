from __future__ import annotations

from pathlib import Path

import pytest

from netpilot.rag import RAGBuildError, chunk_documents, load_documents


def write_document(path: Path, *, body: str = "VPN 用于校外访问校园资源。") -> None:
    path.write_text(
        "---\n"
        "title: VPN 测试指南\n"
        "source: https://example.edu/vpn\n"
        "source_type: official\n"
        "retrieved_at: 2026-08-26\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_loader_preserves_required_source_metadata(tmp_path: Path) -> None:
    write_document(tmp_path / "vpn.md")

    documents = load_documents(tmp_path)

    assert len(documents) == 1
    assert documents[0].title == "VPN 测试指南"
    assert documents[0].source == "https://example.edu/vpn"
    assert documents[0].source_type.value == "official"
    assert documents[0].file == "vpn.md"


def test_loader_rejects_unattributed_knowledge(tmp_path: Path) -> None:
    (tmp_path / "unknown.md").write_text("没有来源的内容", encoding="utf-8")

    with pytest.raises(RAGBuildError, match="front matter"):
        load_documents(tmp_path)


def test_chunking_is_bounded_and_deterministic(tmp_path: Path) -> None:
    body = "\n\n".join(f"第{index}段：校园网络测试内容。" * 8 for index in range(12))
    write_document(tmp_path / "vpn.md", body=body)
    documents = load_documents(tmp_path)

    first = chunk_documents(documents, chunk_size=220, overlap=40)
    second = chunk_documents(documents, chunk_size=220, overlap=40)

    assert len(first) > 1
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(len(chunk.content) <= 220 for chunk in first)
    assert all(chunk.source == "https://example.edu/vpn" for chunk in first)


def test_chunking_rejects_overlap_not_smaller_than_size(tmp_path: Path) -> None:
    write_document(tmp_path / "vpn.md")

    with pytest.raises(ValueError, match="overlap"):
        chunk_documents(load_documents(tmp_path), chunk_size=200, overlap=200)
