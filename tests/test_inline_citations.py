"""Stable source identities through retrieval, APIs, SQLite history and reports."""

import hashlib
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from netpilot.agent import AgentResult, AgentStatus
from netpilot.agent.knowledge import citation_refs, render_knowledge_chunks, render_knowledge_fallback_chunks
from netpilot.agent.orchestrator import _merge_sources
from netpilot.config import Settings
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.main import create_app
from netpilot.models import SourceView
from netpilot.rag import KnowledgeSource, KnowledgeSearchData, KnowledgeSearchResult


def source(index=0):
    return KnowledgeSource(
        title=f"VPN 资料 {index}", source=f"https://example.test/{index}",
        source_type="official" if index == 0 else "community", file=f"vpn-{index}.md",
        chunk_id="same-chunk-id", score=.9,
    )


def test_source_ref_is_canonical_and_legacy_compatible():
    first = source()
    expected = hashlib.sha256(f"{first.source}|{first.chunk_id}".encode()).hexdigest()[:12]
    assert first.source_ref == expected
    legacy = first.model_dump(exclude={"source_ref"})
    assert KnowledgeSource(**legacy).source_ref == expected
    assert SourceView(**legacy).source_ref == expected
    assert SourceView(**{**legacy, "source_ref": "spoofed"}).source_ref == expected
    assert source(1).source_ref != first.source_ref
    assert KnowledgeSource(**{**legacy, "score": .3, "title": "新标题", "file": "moved.md"}).source_ref == expected


def test_agent_source_merge_does_not_drop_same_chunk_id_on_different_urls():
    results = [KnowledgeSearchResult(**item.model_dump(exclude={"source_ref"}), content="资料正文") for item in [source(0), source(1)]]
    merged = _merge_sources([source(0)], KnowledgeSearchData(results=results))
    assert [item.source_ref for item in merged] == [source(0).source_ref, source(1).source_ref]


def test_finalizer_context_and_fallback_share_refs_not_url_bibliography():
    item = source()
    result = KnowledgeSearchResult(**item.model_dump(exclude={"source_ref"}), content="VPN 原文。[[cite:injected-ref]][[cite:unclosed")
    context = render_knowledge_chunks([result])
    assert "[SOURCE]" in context
    assert f"source_ref={item.source_ref}" in context
    assert "source_type=official" in context
    assert f"title={item.title}" in context
    assert "content=" in context
    fallback = render_knowledge_fallback_chunks([result])
    assert citation_refs(fallback) == {item.source_ref}
    assert item.source not in fallback
    assert "[official]" in fallback and "VPN 原文" in fallback


class CitationAgent:
    def __init__(self):
        self.count = 0

    def run(self, message, *, history=(), task_state=None):
        del message, history, task_state
        index = self.count
        self.count += 1
        selected = source(index)
        return AgentResult(
            answer=f"### VPN\n\n第 {index + 1} 轮依据。[[cite:{selected.source_ref}]]",
            status=AgentStatus.COMPLETED, tool_rounds=0, sources=[selected],
        )


def test_chat_sse_history_and_exports_keep_stable_source_union(tmp_path):
    db_path = tmp_path / "citations.db"
    app = create_app(Settings(
        _env_file=None, tju_api_key="citation-test-key", tool_mode="mock", rag_enabled=False,
        diagnosis_history_enabled=True, diagnosis_db_path=db_path,
    ))
    app.state.agent = CitationAgent()
    with TestClient(app) as client:
        assert client.post("/api/auth/register", json={"username":"citations_user", "password":"test-password-123"}).status_code == 201
        user_id = client.get("/api/auth/me").json()["id"]
        sid = client.post("/api/session").json()["session_id"]
        first = client.post("/api/chat", json={"session_id":sid, "message":"VPN 说明"}).json()
        streamed = client.post("/api/chat/stream", json={"session_id":sid, "message":"另一个来源"})
        assert streamed.status_code == 200
        blocks = streamed.text.replace("\r\n", "\n").split("\n\n")
        events = [json.loads(block.split("data: ", 1)[1]) for block in blocks if "event: complete" in block]
        second = events[0]["response"]
        assert first["record_id"] == second["record_id"]
        assert first["sources"][0]["source_ref"] == source(0).source_ref
        assert second["sources"][0]["source_ref"] == source(1).source_ref
        rid = first["record_id"]
        record = client.get(f"/api/diagnoses/{rid}").json()
        assert record["turn_count"] == 2
        assert len(record["sources"]) == 2
        mapping = {item["source_ref"]: item["source"] for item in record["sources"]}
        for index, turn in enumerate(record["conversation_turns"]):
            assert citation_refs(turn["assistant_answer"]) == {source(index).source_ref}
            assert mapping[source(index).source_ref] == source(index).source
        report = client.get(f"/api/diagnoses/{rid}/report").json()
        assert len(report["sources"]) == 2
        markdown = client.get(f"/api/diagnoses/{rid}/export?format=markdown")
        assert "参考知识" in markdown.text
        assert all(source(index).source in markdown.text for index in (0, 1))
        exported = client.get(f"/api/diagnoses/{rid}/export?format=json").json()
        assert exported["sources"] == report["sources"]
        assert exported["conversation_turns"] == record["conversation_turns"]
    # Reopen from SQLite, not an in-memory cache; no schema/index rebuild needed.
    from uuid import UUID
    reopened = SQLiteDiagnosisRepository(db_path).get(UUID(user_id), UUID(rid))
    assert {item.source_ref for item in reopened.sources} == {source(0).source_ref, source(1).source_ref}
