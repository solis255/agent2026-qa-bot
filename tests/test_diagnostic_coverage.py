from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from netpilot.agent import (
    AgentOrchestrator,
    AgentToolStep,
    DiagnosticGoal,
    ToolRegistry,
    assess_evidence_sufficiency,
    coverage_from_observations,
    track_hypotheses,
)
from netpilot.agent.diagnosis import build_diagnostic_answer
from netpilot.config import Settings
from netpilot.llm import ChatMessage, ChatResult, FunctionCall, ToolCall
from netpilot.tools import build_network_tools
from netpilot.tools.schemas import (
    DNSLookupData,
    HTTPCheckData,
    NetworkInfoData,
    PingData,
    ToolResult,
)


def _call(call_id: str, name: str, arguments: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments=arguments),
    )


def _result(
    content: str | None = None,
    *,
    calls: list[ToolCall] | None = None,
) -> ChatResult:
    return ChatResult(
        content=content,
        tool_calls=calls or [],
        model="fake-tju-llm",
        duration_ms=1,
    )


class CoverageLLM:
    def __init__(self) -> None:
        self.responses = [
            _result(
                calls=[
                    _call("dns-first", "dns_lookup", '{"domain":"github.com"}')
                ]
            ),
            _result(
                calls=[
                    _call("config", "get_network_info", "{}"),
                    _call("public-ip", "ping_host", '{"host":"1.1.1.1","count":1}'),
                    _call("http", "http_check", '{"url":"https://github.com"}'),
                ]
            ),
            _result("已完成完整网页故障诊断。"),
        ]
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
        self.calls.append({"messages": list(messages), **kwargs})
        return self.responses.pop(0)


class SequenceLLM:
    def __init__(self, responses: list[ChatResult]) -> None:
        self.responses = list(responses)

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
        del messages, kwargs
        return self.responses.pop(0)


def _dns_step(call_id: str, domain: str) -> AgentToolStep:
    return AgentToolStep(
        round=1,
        tool_call_id=call_id,
        tool_name="dns_lookup",
        arguments={"domain": domain},
        result=ToolResult[DNSLookupData](
            success=True,
            tool="dns_lookup",
            summary="域名解析失败",
            data=DNSLookupData(resolved=False, addresses=[]),
            duration_ms=1,
        ),
    )


def _ping_step() -> AgentToolStep:
    return AgentToolStep(
        round=1,
        tool_call_id="public-ip",
        tool_name="ping_host",
        arguments={"host": "1.1.1.1", "count": 1},
        result=ToolResult[PingData](
            success=True,
            tool="ping_host",
            summary="公网 IP 可达",
            data=PingData(
                reachable=True,
                packet_loss=0,
                avg_latency_ms=10,
                transmitted=1,
                received=1,
            ),
            duration_ms=1,
        ),
    )


def _config_step() -> AgentToolStep:
    return AgentToolStep(
        round=1,
        tool_call_id="config",
        tool_name="get_network_info",
        arguments={},
        result=ToolResult[NetworkInfoData](
            success=True,
            tool="get_network_info",
            summary="网络配置已读取",
            data=NetworkInfoData(
                ipv4=["10.0.0.2"],
                default_gateway="10.0.0.1",
                dns_servers=["10.0.0.53"],
            ),
            duration_ms=1,
        ),
    )


def _http_step() -> AgentToolStep:
    return AgentToolStep(
        round=1,
        tool_call_id="http",
        tool_name="http_check",
        arguments={"url": "https://github.com"},
        result=ToolResult[HTTPCheckData](
            success=True,
            tool="http_check",
            summary="HTTP 请求未成功",
            data=HTTPCheckData(
                reachable=False,
                request_sent=True,
                failure_reason="dns_resolution_failed",
            ),
            duration_ms=1,
        ),
    )


def test_full_web_goal_requires_cross_layer_coverage() -> None:
    message = "浏览器打开大部分网站都失败，请按照实际网络排障流程完整诊断。"
    partial = coverage_from_observations(
        steps=[_dns_step("dns", "github.com")]
    )
    partial_result = assess_evidence_sufficiency(
        message,
        partial,
        diagnostic=True,
    )

    complete = coverage_from_observations(
        steps=[
            _dns_step("dns", "github.com"),
            _config_step(),
            _ping_step(),
            _http_step(),
        ]
    )
    complete_result = assess_evidence_sufficiency(
        message,
        complete,
        diagnostic=True,
    )

    assert partial_result.goal is DiagnosticGoal.FULL_WEB_DIAGNOSIS
    assert partial_result.sufficient is False
    assert partial_result.missing_coverage == [
        "network_config",
        "ip_connectivity",
        "application",
    ]
    assert complete_result.sufficient is True


def test_full_web_diagnosis_continues_after_first_dns_abnormal() -> None:
    settings = Settings(
        _env_file=None,
        tool_mode="mock",
        mock_scenario="dns_failure",
    )
    llm = CoverageLLM()
    agent = AgentOrchestrator(llm, ToolRegistry(build_network_tools(settings)))

    result = agent.run(
        "浏览器打开大部分网站都失败，请按照实际网络排障流程完整诊断。"
    )

    assert [step.tool_name for step in result.steps] == [
        "dns_lookup",
        "get_network_info",
        "ping_host",
        "http_check",
    ]
    assert result.coverage.network_config_checked is True
    assert result.coverage.dns_checked is True
    assert result.coverage.ip_connectivity_checked is True
    assert result.coverage.http_checked is True
    assert result.evidence_sufficiency is not None
    assert result.evidence_sufficiency.sufficient is True
    assert llm.calls[1]["tool_choice"] == "auto"
    assert any(
        "DIAGNOSTIC COVERAGE INCOMPLETE" in (message.content or "")
        for message in llm.calls[1]["messages"]
    )
    assert llm.calls[2]["tool_choice"] == "none"


def test_hypotheses_use_supporting_and_contradicting_evidence() -> None:
    hypotheses = {
        item.name: item
        for item in track_hypotheses(
            steps=[
                _dns_step("dns-github", "github.com"),
                _dns_step("dns-baidu", "baidu.com"),
                _ping_step(),
            ]
        )
    }

    assert hypotheses["dns_resolution_path_failure"].status == "supported"
    assert hypotheses["single_site_failure"].status == "weakened"
    assert hypotheses["overall_ip_connectivity_failure"].status == "excluded"
    assert hypotheses["overall_ip_connectivity_failure"].contradicting_evidence_ids == [
        "tool_call:public-ip"
    ]


def test_repeated_dns_evidence_is_aggregated_under_one_heading() -> None:
    answer = build_diagnostic_answer(
        [
            _dns_step("dns-github", "github.com"),
            _dns_step("dns-baidu", "baidu.com"),
            _dns_step("dns-tju", "tju.edu.cn"),
        ]
    )

    assert answer.count("DNS 解析：发现异常") == 1
    assert "github.com：域名解析失败" in answer
    assert "baidu.com：域名解析失败" in answer
    assert "tju.edu.cn：域名解析失败" in answer


def test_adjacent_duplicate_model_conclusions_are_removed() -> None:
    settings = Settings(
        _env_file=None,
        tool_mode="mock",
        mock_scenario="dns_failure",
    )
    llm = SequenceLLM(
        [
            _result(
                calls=[
                    _call("dns", "dns_lookup", '{"domain":"github.com"}')
                ]
            ),
            _result("DNS 解析异常\nDNS 解析异常\n建议检查 DNS 配置。"),
        ]
    )

    result = AgentOrchestrator(
        llm,
        ToolRegistry(build_network_tools(settings)),
    ).run("请检查 DNS 是否异常")

    assert result.answer.count("DNS 解析异常") == 1
