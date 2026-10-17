from __future__ import annotations

import pytest

from netpilot.agent import TurnIntent, classify_turn_intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("请检查 github.com 为什么打不开", TurnIntent.DIAGNOSE),
        ("网络有问题", TurnIntent.CLARIFY),
        ("请基于刚才结果继续分析", TurnIntent.ANALYZE_EXISTING),
        ("天津大学 VPN 怎么使用？请检索知识库", TurnIntent.KNOWLEDGE_REQUEST),
        ("把这次排障整理成报告", TurnIntent.REPORT_REQUEST),
        ("这更像 DNS 配置错误还是代理问题？", TurnIntent.COMPARE),
        ("我下一步应该怎么做？", TurnIntent.FOLLOWUP_ACTION),
        ("你刚才没有回答我的问题", TurnIntent.META_FEEDBACK),
        ("你刚才没有按照我的要求回复，只是重复答案", TurnIntent.META_FEEDBACK),
        ("我修改 DNS 后现在情况变了", TurnIntent.STATE_CHANGED),
        ("我修改 DNS 后仍然打不开网页", TurnIntent.STATE_CHANGED),
        ("DNS 是什么？", TurnIntent.GENERAL_QUESTION),
    ],
)
def test_classifies_all_milestone_10b_turn_intents(
    message: str,
    expected: TurnIntent,
) -> None:
    result = classify_turn_intent(message, has_evidence=True)

    assert result.intent is expected


def test_do_not_recheck_wording_is_analysis_not_state_change() -> None:
    result = classify_turn_intent(
        "请基于刚才结果继续分析，不要重新检测。",
        has_evidence=True,
    )

    assert result.intent is TurnIntent.ANALYZE_EXISTING
    assert result.force_recheck is False


def test_explicit_recheck_invalidates_prior_observations() -> None:
    result = classify_turn_intent("请重新检测一次 DNS")

    assert result.intent is TurnIntent.STATE_CHANGED
    assert result.force_recheck is True
    assert result.needs_tools is True


@pytest.mark.parametrize("message", [
    "请检索知识库，比较天津大学 VPN 和 eduroam 的使用区别。",
    "比较校园网 VPN 和 eduroam，标出官方资料来源。",
    "天津大学 VPN 怎么使用？还是请检索知识库并标出来源。",
    "基于刚才结果，结合知识库分析 DNS 与代理故障的区别。",
    "请调用 knowledge_search 比较 VPN 的使用方式。",
    "比较天津大学 VPN 与 eduroam。",
    "不要重新检测，请检索知识库比较 DNS 和代理问题。",
])
def test_sourced_comparison_is_knowledge_request(message: str) -> None:
    result = classify_turn_intent(message, has_evidence=True)
    assert result.intent is TurnIntent.KNOWLEDGE_REQUEST
    assert result.needs_rag is True
    assert result.needs_tools is False


@pytest.mark.parametrize("message", [
    "请比较刚才的 DNS 与 TCP 证据，不要检索知识库。",
    "不需要查询知识库，只比较已有证据。",
    "比较 VPN 与 eduroam，不用知识库。",
])
def test_negated_retrieval_keeps_evidence_only_comparison(message: str) -> None:
    result = classify_turn_intent(message, has_evidence=True)
    assert result.intent is TurnIntent.COMPARE
    assert result.needs_rag is False


@pytest.mark.parametrize("message", [
    "基于刚才的 VPN 连接结果继续分析。",
    "根据上一轮的校园网连接检测结果继续分析。",
])
def test_campus_topic_does_not_override_explicit_existing_evidence_analysis(message):
    result = classify_turn_intent(message, has_evidence=True)
    assert result.intent is TurnIntent.ANALYZE_EXISTING
    assert result.needs_rag is False


def test_history_keeps_priority_with_explicit_or_negated_rag() -> None:
    allowed = classify_turn_intent("结合知识库比较今天的诊断记录。")
    blocked = classify_turn_intent("比较今天的诊断记录，不要检索知识库。")
    assert allowed.intent is blocked.intent is TurnIntent.HISTORY_ANALYSIS
    assert allowed.needs_rag is True
    assert blocked.needs_rag is False


@pytest.mark.parametrize("message,intent", [
    ("整理成报告，对比结果并检索知识库。", TurnIntent.REPORT_REQUEST),
    ("你刚才没有回答我的问题，请比较知识库资料。", TurnIntent.META_FEEDBACK),
])
def test_report_and_meta_keep_their_tool_free_contract(message, intent) -> None:
    result = classify_turn_intent(message)
    assert result.intent is intent
    assert result.needs_rag is False
