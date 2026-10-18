"""Bounded retrieval excerpts shared by context, finalization and fallback."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING
import re

from netpilot.rag import KnowledgeSearchData, KnowledgeSearchResult, KnowledgeSource
from netpilot.rag.schemas import source_ref_for


CITATION_MARKER = re.compile(r"\[\[cite:([^\]\n]*)\]\]")


def citation_refs(content: str) -> set[str]:
    return {
        ref.strip()
        for match in CITATION_MARKER.finditer(content)
        for ref in match[1].split(",")
    }


def _fallback_excerpt(content: str) -> str:
    # Reference text cannot introduce its own citation protocol, even unfinished.
    return excerpt(re.sub(r"\[\[cite:[^\]\n]*(?:\]\]|$)", "", content))

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
        f"[SOURCE]\nsource_ref={source_ref_for(item.source, item.chunk_id)}\n"
        f"source_type={item.source_type.value}\ntitle={item.title[:200]}\n"
        f"content=\n{excerpt(item.content, chunk_chars)}"
        for item in results
    )


def render_knowledge_fallback_chunks(results: Iterable[KnowledgeSearchResult]) -> str:
    """Attach provenance to each excerpt, never a fabricated paragraph mapping."""

    return "\n\n".join(
        f"[{item.source_type.value}] {item.title[:200]}\n\n"
        f"{_fallback_excerpt(item.content)}[[cite:{source_ref_for(item.source, item.chunk_id)}]]"
        for item in results
    )


def result_sources(results: Iterable[KnowledgeSearchResult]) -> list[KnowledgeSource]:
    return [
        KnowledgeSource(**item.model_dump(exclude={"content"}))
        for item in results
    ]


def source_only_answer(content: str, results: Iterable[KnowledgeSearchResult]) -> bool:
    """Reject citation lists that contain no substantive answer body."""

    chunks = list(results)
    content = CITATION_MARKER.sub("", content)
    for line in content.splitlines():
        if re.fullmatch(
            r"(?:参考来源|资料来源|来源|参考资料|参考文献|检索结果|sources?)(?:如下|列表)?\s*[:：]?",
            line.strip().strip("#* "), flags=re.IGNORECASE,
        ):
            continue
        if re.match(r"\s*(?:[-*+]|\d+[.)、])?\s*\[(?:official|community|maintainer)\]", line, flags=re.IGNORECASE):
            without_url = re.sub(r"https?://[^\s)<>]+", "", line)
            if "http" in line and not re.search(r"[。！？；，]", without_url):
                continue
        body = line
        for item in chunks:
            body = body.replace(item.title, "").replace(item.chunk_id, "")
        body = re.sub(r"https?://[^\s)<>]+", "", body)
        body = re.sub(r"\[(?:official|community|maintainer)\]", "", body, flags=re.IGNORECASE)
        body = re.sub(r"(?:Source[s]?|来源|参考资料|参考文献|检索结果)\s*[:：]?", "", body, flags=re.IGNORECASE)
        body = re.sub(r"[\W_\d]+", "", body)
        # Citation headings are not prose, but a short substantive Chinese
        # instruction such as “先认证。” is still an answer (three characters).
        if body and body not in {"资料", "标题", "URL", "以下", "如下", "参考来源"}:
            return False
    return True


def is_knowledge_followup(user_message: str) -> bool:
    """Recognize filtering/formatting existing sources, not a fresh search."""

    if re.search(r"检索|搜索|查询|查找|查阅|knowledge_search", user_message, flags=re.IGNORECASE):
        return False
    return bool(re.search(
        r"community|official|maintainer|source_type|这些(?:资料|内容|来源)|"
        r"上述(?:资料|内容|来源)|(?:刚才|之前).{0,8}(?:资料|内容|来源)|其中",
        user_message, flags=re.IGNORECASE,
    ))
