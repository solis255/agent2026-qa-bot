"""Bounded retrieval excerpts shared by context, finalization and fallback."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING
import re

from netpilot.rag import KnowledgeSearchData, KnowledgeSearchResult, KnowledgeSource

if TYPE_CHECKING:
    from netpilot.agent.schemas import AgentToolStep
    from netpilot.agent.task_state import EvidenceRecord


def knowledge_results(
    evidence: Iterable[EvidenceRecord] = (),
    steps: Iterable[AgentToolStep] = (),
) -> list[KnowledgeSearchResult]:
    """Keep the best six unique chunks; full results remain in Tool Evidence."""

    found: dict[tuple[str, str, str], KnowledgeSearchResult] = {}
    data_items = [r.data for r in evidence if r.tool_name == "knowledge_search"]
    data_items += [s.result.data for s in steps if s.tool_name == "knowledge_search"]
    for data in data_items:
        try:
            parsed = KnowledgeSearchData.model_validate(data)
        except (TypeError, ValueError):
            continue
        for item in parsed.results:
            key = (item.source, item.file, item.chunk_id)
            if key not in found or item.score > found[key].score:
                found[key] = item
    return sorted(found.values(), key=lambda item: item.score, reverse=True)[:6]


def excerpt(value: str, limit: int = 900) -> str:
    """Remove control characters and render retrieved text as quoted data."""

    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    cleaned = cleaned[:limit] + ("…" if len(cleaned) > limit else "")
    return "\n".join(
        "> " + line.replace("<", "&lt;").replace(">", "&gt;")
        for line in cleaned.splitlines()
    )


def render_knowledge_chunks(
    results: Iterable[KnowledgeSearchResult], *, chunk_chars: int = 900
) -> str:
    return "\n\n".join(
        f"[{item.source_type.value}] {item.title[:200]}\n"
        f"chunk={item.chunk_id}; score={item.score:.3f}\n"
        f"{excerpt(item.content, chunk_chars)}\n来源：{item.source}"
        for item in results
    )


def result_sources(results: Iterable[KnowledgeSearchResult]) -> list[KnowledgeSource]:
    return [
        KnowledgeSource(**item.model_dump(exclude={"content"}))
        for item in results
    ]


def source_only_answer(content: str, results: Iterable[KnowledgeSearchResult]) -> bool:
    """Reject citation lists that contain no substantive answer body."""

    body = content
    for item in results:
        body = body.replace(item.title, "").replace(item.chunk_id, "")
    body = re.sub(r"https?://[^\s)<>]+", "", body)
    body = re.sub(r"official|community|maintainer|Source[s]?|来源|参考资料|参考文献|检索结果", "", body, flags=re.IGNORECASE)
    body = re.sub(r"[\W_\d]+", "", body)
    return len(body) < 6
