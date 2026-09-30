"""Deterministic, high-confidence classification for one user turn."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TurnIntent(str, Enum):
    DIAGNOSE = "diagnose"
    CLARIFY = "clarify"
    ANALYZE_EXISTING = "analyze_existing"
    KNOWLEDGE_REQUEST = "knowledge_request"
    REPORT_REQUEST = "report_request"
    COMPARE = "compare"
    FOLLOWUP_ACTION = "followup_action"
    META_FEEDBACK = "meta_feedback"
    STATE_CHANGED = "state_changed"
    GENERAL_QUESTION = "general_question"


class IntentClassification(BaseModel):
    """Policy-relevant interpretation of the current user turn."""

    model_config = ConfigDict(extra="forbid")

    intent: TurnIntent
    confidence: float = Field(ge=0, le=1)
    needs_tools: bool
    needs_rag: bool
    force_recheck: bool = False
    reason: str = Field(min_length=1)


_STATE_CHANGE_PATTERNS = (
    r"重新连接(?:了|过)?(?:网络|校园网|wi-?fi|无线|有线)?",
    r"(?:修改|更换|设置)(?:了)?\s*(?:dns|代理|proxy|网关|网络)\s*后",
    r"现在(?:的)?(?:情况|状态|现象).{0,4}(?:变了|有变化|不一样)",
    r"(?:修复|调整|重启|切换).{0,8}后(?:又|现在|仍|还)",
)

_RECHECK_TERMS = (
    "重新检查",
    "重新检测",
    "重新诊断",
    "再检查一次",
    "再检测一次",
    "再测一次",
)

_META_TERMS = (
    "你没有回答",
    "你没回答",
    "没按要求回复",
    "没有按要求回复",
    "答非所问",
    "一直重复",
    "重复回答",
    "同一个回答",
    "你理解错了",
    "你刚才说错",
)

_REPORT_TERMS = (
    "生成报告",
    "诊断报告",
    "运维报告",
    "运维摘要",
    "诊断摘要",
    "排障摘要",
    "总结本次诊断",
    "整理成报告",
    "整理成一份",
)

_COMPARE_TERMS = (
    "比较",
    "对比",
    "区别",
    "差异",
    "更像",
    "哪个更",
    "还是",
)

_EXISTING_TERMS = (
    "基于刚才",
    "根据刚才",
    "基于上一轮",
    "根据上一轮",
    "基于已有",
    "已有证据",
    "检测结果",
    "继续分析",
    "不要重新",
    "刚才发现",
    "刚才的结果",
)

_KNOWLEDGE_TERMS = (
    "知识库",
    "校园资料",
    "官方资料",
    "相关资料",
    "参考资料",
    "文档",
    "政策",
    "来源",
)

_CAMPUS_TERMS = (
    "天津大学",
    "天大",
    "校园网",
    "tjuwlan",
    "eduroam",
    "统一身份认证",
    "vpn",
)

_INFORMATION_TERMS = (
    "怎么",
    "如何",
    "配置",
    "开通",
    "使用",
    "入口",
    "账号",
    "资费",
    "规定",
    "政策",
    "说明",
    "资料",
    "文档",
    "连接",
)

_FOLLOWUP_TERMS = (
    "下一步",
    "接下来",
    "怎么处理",
    "如何处理",
    "应该怎么做",
    "该怎么办",
    "修复建议",
    "解决顺序",
)

_DIAGNOSE_TERMS = (
    "检查",
    "检测",
    "诊断",
    "排查",
    "打不开",
    "连不上",
    "无法连接",
    "解析失败",
    "超时",
    "丢包",
    "断网",
    "异常",
    "故障",
    "ping_host",
    "dns_lookup",
    "tcp_check",
    "http_check",
    "traceroute",
    "get_network_info",
)

_AMBIGUOUS_FAULTS = {
    "网络有问题",
    "网络不行",
    "上不了网",
    "上网有问题",
    "断网了",
    "网页打不开",
    "连不上网",
}


def classify_turn_intent(
    message: str,
    *,
    has_evidence: bool = False,
) -> IntentClassification:
    """Classify a turn without granting the model any execution authority."""

    text = " ".join(message.strip().casefold().split())
    compact = re.sub(r"[\s，。！？,!?;；:：]+", "", text)

    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _STATE_CHANGE_PATTERNS):
        return _classification(
            TurnIntent.STATE_CHANGED, 0.98, tools=True,
            reason="explicit network state change",
        )
    recheck_requested = any(term in text for term in _RECHECK_TERMS)
    recheck_negated = bool(
        re.search(r"(?:不要|无需|不必|别).{0,4}(?:重新|再)(?:检查|检测|诊断)", text)
    )
    if recheck_requested and not recheck_negated:
        return _classification(
            TurnIntent.STATE_CHANGED, 0.96, tools=True, force_recheck=True,
            reason="explicit request to refresh observations",
        )
    meta_context = any(term in text for term in ("你刚才", "你之前", "上一轮"))
    meta_complaint = any(
        term in text
        for term in (
            "没有按照",
            "没有按",
            "没按",
            "没有回答",
            "没回答",
            "重复",
            "偏题",
            "不对",
        )
    )
    if any(term in text for term in _META_TERMS) or (
        meta_context and meta_complaint
    ):
        return _classification(
            TurnIntent.META_FEEDBACK, 0.98,
            reason="feedback about the assistant's prior response",
        )
    if any(term in text for term in _REPORT_TERMS):
        return _classification(
            TurnIntent.REPORT_REQUEST, 0.98,
            reason="request to format existing work as a report",
        )
    if any(term in text for term in _COMPARE_TERMS):
        return _classification(
            TurnIntent.COMPARE, 0.9,
            reason="comparison between candidate explanations",
        )
    if any(term in text for term in _EXISTING_TERMS) or (
        has_evidence and compact in {"分析一下", "继续分析", "刚才发现了什么"}
    ):
        return _classification(
            TurnIntent.ANALYZE_EXISTING, 0.95,
            reason="request explicitly refers to existing observations",
        )
    if any(term in text for term in _KNOWLEDGE_TERMS) or (
        any(term in text for term in _CAMPUS_TERMS)
        and any(term in text for term in _INFORMATION_TERMS)
    ):
        return _classification(
            TurnIntent.KNOWLEDGE_REQUEST, 0.94, rag=True,
            reason="campus information or sourced documentation request",
        )
    if compact in _AMBIGUOUS_FAULTS:
        return _classification(
            TurnIntent.CLARIFY, 0.97,
            reason="fault description lacks a target or observable scope",
        )
    if any(term in text for term in _FOLLOWUP_TERMS):
        return _classification(
            TurnIntent.FOLLOWUP_ACTION, 0.9,
            reason="request for the next safe action",
        )
    if any(term in text for term in _DIAGNOSE_TERMS):
        return _classification(
            TurnIntent.DIAGNOSE, 0.9, tools=True,
            reason="concrete diagnosis or read-only check request",
        )
    return _classification(
        TurnIntent.GENERAL_QUESTION, 0.72,
        reason="no high-confidence diagnostic or task-control signal",
    )


def _classification(
    intent: TurnIntent,
    confidence: float,
    *,
    tools: bool = False,
    rag: bool = False,
    force_recheck: bool = False,
    reason: str,
) -> IntentClassification:
    return IntentClassification(
        intent=intent,
        confidence=confidence,
        needs_tools=tools,
        needs_rag=rag,
        force_recheck=force_recheck,
        reason=reason,
    )
