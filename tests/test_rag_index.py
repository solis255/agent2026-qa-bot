from __future__ import annotations

from pathlib import Path

import pytest

from netpilot.rag import (
    DeterministicHashEmbedding,
    FaissRetriever,
    KnowledgeDocument,
    RAGIndexError,
    build_index,
    chunk_documents,
    load_index,
)


def build_test_index(index_dir: Path):
    documents = [
        KnowledgeDocument(
            title="VPN 测试指南",
            source="https://example.edu/vpn",
            source_type="official",
            file="vpn.md",
            content="VPN 用于校外访问校园资源。先激活账号，再安装客户端连接。",
        ),
        KnowledgeDocument(
            title="无线网测试指南",
            source="https://example.edu/wifi",
            source_type="official",
            file="wifi.md",
            content="连接 tjuwlan 后，通过浏览器打开认证页面完成无线网络登录。",
        ),
    ]
    chunks = chunk_documents(documents, chunk_size=220, overlap=40)
    embedder = DeterministicHashEmbedding()
    manifest = build_index(
        chunks,
        embedder,
        index_dir,
        document_count=len(documents),
        chunk_size=220,
        chunk_overlap=40,
    )
    return chunks, embedder, manifest


def test_index_round_trip_preserves_vectors_and_sources(tmp_path: Path) -> None:
    chunks, embedder, manifest = build_test_index(tmp_path)

    vector_index, loaded_chunks, loaded_manifest = load_index(
        tmp_path,
        expected_model=embedder.model_name,
    )

    assert vector_index.ntotal == len(chunks)
    assert loaded_chunks == chunks
    assert loaded_manifest == manifest


def test_retriever_returns_ranked_source_metadata(tmp_path: Path) -> None:
    _chunks, embedder, _manifest = build_test_index(tmp_path)
    retriever = FaissRetriever.open(tmp_path, embedder, top_k=2, min_score=-1)

    results = retriever.search("VPN 怎么使用？")

    assert len(results) == 2
    assert results[0].title == "VPN 测试指南"
    assert results[0].source == "https://example.edu/vpn"
    assert results[0].chunk_id
    assert results[0].score >= results[1].score


def test_retriever_returns_empty_when_evidence_is_below_threshold(tmp_path: Path) -> None:
    _chunks, embedder, _manifest = build_test_index(tmp_path)
    retriever = FaissRetriever.open(tmp_path, embedder, min_score=1.0)

    assert retriever.search("完全无关的问题") == []


def test_index_rejects_embedding_model_mismatch(tmp_path: Path) -> None:
    build_test_index(tmp_path)

    with pytest.raises(RAGIndexError, match="模型不匹配"):
        load_index(tmp_path, expected_model="another/model")


def test_index_rejects_incomplete_files(tmp_path: Path) -> None:
    with pytest.raises(RAGIndexError, match="不存在或不完整"):
        load_index(tmp_path, expected_model="test/model")
