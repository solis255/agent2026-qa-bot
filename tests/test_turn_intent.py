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
