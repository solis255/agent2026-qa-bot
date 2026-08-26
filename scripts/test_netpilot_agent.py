#!/usr/bin/env python3
"""Run the Milestone 4 Agent against tju-llm and an offline DNS failure mock."""

from __future__ import annotations

import sys

from pydantic import ValidationError

from netpilot.agent import AgentOrchestrator, AgentStatus, ToolRegistry
from netpilot.config import Settings
from netpilot.llm import TJUClient
from netpilot.tools import build_network_tools


def _configure_windows_console() -> None:
    """Keep Chinese acceptance-test output readable in Windows terminals."""

    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    """Verify a real native tool-call loop without probing the local network."""

    _configure_windows_console()
    try:
        settings = Settings(tool_mode="mock", mock_scenario="dns_failure")
    except ValidationError as exc:
        print(f"NetPilot 配置无效：{exc.error_count()} 个字段未通过校验。")
        return 1

    client = TJUClient(settings)
    if not client.configured:
        print("未配置 TJU_API_KEY。请在项目根目录 .env 文件中填写 API Key。")
        return 1

    registry = ToolRegistry(build_network_tools(settings))
    agent = AgentOrchestrator(
        client,
        registry,
        max_tool_rounds=settings.max_tool_rounds,
    )
    try:
        result = agent.run(
            "我可以访问公网 IP，但打不开 github.com。请自动诊断；"
            "至少分别使用 ping_host 检查 1.1.1.1，并使用 dns_lookup 检查 github.com，"
            "最后给出问题判断、证据、可能原因和建议。"
        )
    finally:
        client.close()

    print(f"状态：{result.status.value}，工具轮次：{result.tool_rounds}")
    for step in result.steps:
        print(
            f"[{step.round}] {step.tool_name} "
            f"({step.tool_call_id}) -> {step.result.summary}"
        )
    print("\n最终诊断：")
    print(result.answer)
    if settings.tju_show_token_usage:
        print(f"\nToken 用量：{result.usage.total_tokens}")
    print(f"模型总耗时：{result.llm_duration_ms:.0f} ms")

    called_tools = {step.tool_name for step in result.steps}
    expected_tools = {"ping_host", "dns_lookup"}
    if result.status is not AgentStatus.COMPLETED:
        print("验收失败：Agent 未正常完成诊断。")
        return 1
    if not expected_tools.issubset(called_tools):
        print("验收失败：模型没有执行所要求的 Ping 与 DNS 检查。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
