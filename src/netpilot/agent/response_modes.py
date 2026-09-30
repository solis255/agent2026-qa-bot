"""Response-mode selection and model guidance for classified turns."""

from __future__ import annotations

from enum import Enum

from netpilot.agent.intent import TurnIntent
from netpilot.llm import ChatMessage, ChatRole


class ResponseMode(str, Enum):
    DIAGNOSTIC = "diagnostic"
    ANALYSIS = "analysis"
    KNOWLEDGE = "knowledge"
    REPORT = "report"
    COMPARISON = "comparison"
    CLARIFICATION = "clarification"
    META = "meta"


_MODE_BY_INTENT = {
    TurnIntent.DIAGNOSE: ResponseMode.DIAGNOSTIC,
    TurnIntent.CLARIFY: ResponseMode.CLARIFICATION,
    TurnIntent.ANALYZE_EXISTING: ResponseMode.ANALYSIS,
    TurnIntent.KNOWLEDGE_REQUEST: ResponseMode.KNOWLEDGE,
    TurnIntent.REPORT_REQUEST: ResponseMode.REPORT,
    TurnIntent.COMPARE: ResponseMode.COMPARISON,
    TurnIntent.FOLLOWUP_ACTION: ResponseMode.ANALYSIS,
    TurnIntent.META_FEEDBACK: ResponseMode.META,
    TurnIntent.STATE_CHANGED: ResponseMode.DIAGNOSTIC,
    TurnIntent.GENERAL_QUESTION: ResponseMode.KNOWLEDGE,
}


_INSTRUCTIONS = {
    ResponseMode.DIAGNOSTIC: (
        "当前是实时诊断模式。只调用当前目标必要的只读工具，"
        "结论必须对应结构化证据。"
    ),
    ResponseMode.CLARIFICATION: (
        "当前是澄清模式，不得调用任何工具。不要猜测故障；"
        "请简洁询问连接类型、影响范围、是否所有站点受影响、"
        "聊天软件是否正常以及 VPN/Proxy 状态中最必要的信息。"
    ),
    ResponseMode.ANALYSIS: (
        "当前是已有证据分析/后续建议模式，不得调用任何工具。"
        "明确说明已有证据能证明什么、不能证明什么，并给出最小干预的下一步。"
    ),
    ResponseMode.KNOWLEDGE: (
        "当前是知识问答模式。若提供 knowledge_search，只可使用其检索参考资料；"
        "不得调用网络状态检测工具。列出真实来源，无资料时明确说明。"
    ),
    ResponseMode.REPORT: (
        "当前是报告模式，不得调用网络工具或知识检索。"
        "仅基于对话和现有 Evidence，严格使用“现象 / 检测步骤 / 证据 / "
        "排除项 / 初步结论 / 建议”六个标题；证据不足的栏目必须如实标注。"
    ),
    ResponseMode.COMPARISON: (
        "当前是比较模式，不得调用任何工具。"
        "用已有 Evidence 分别列出支持、反证和缺失证据，不得将可能性写成已确认事实。"
    ),
    ResponseMode.META: (
        "当前是元反馈模式，不得调用网络工具或知识检索。"
        "直接回应用户指出的偏差，简短说明如何修正，并仅基于已有状态重新回答。"
    ),
}


def response_mode_for(intent: TurnIntent) -> ResponseMode:
    return _MODE_BY_INTENT[intent]


def response_mode_message(mode: ResponseMode) -> ChatMessage:
    return ChatMessage(
        role=ChatRole.SYSTEM,
        content=f"TURN RESPONSE MODE: {mode.value}\n{_INSTRUCTIONS[mode]}",
    )


def clarification_answer() -> str:
    """Return a deterministic first clarification without running the model."""

    return (
        "为了避免无意义的检测，请先补充以下信息：\n"
        "1. 当前使用 Wi-Fi 还是有线网络？\n"
        "2. 是所有网站都打不开，还是只有特定网站/服务？\n"
        "3. 微信、QQ 等聊天软件是否能正常收发消息？\n"
        "4. 当前是否开启 VPN 或系统/浏览器代理？"
    )
