#!/usr/bin/env python3
"""Verify Milestone 5 with tju-llm and the persisted local knowledge index."""

from __future__ import annotations

import sys

from pydantic import ValidationError

from netpilot.agent import AgentOrchestrator, AgentStatus, ToolRegistry
from netpilot.config import Settings
from netpilot.llm import TJUClient
from netpilot.rag import load_configured_retriever
from netpilot.tools import build_network_tools


def _configure_windows_console() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _configure_windows_console()
    try:
        settings = Settings(tool_mode="mock", rag_enabled=True)
    except ValidationError as exc:
        print(f"NetPilot 配置无效：{exc.error_count()} 个字段未通过校验。")
        return 1

    retriever = load_configured_retriever(settings)
    if retriever is None:
        print("RAG 尚未就绪，请先运行 scripts\\build_knowledge_index.py。")
        return 1
    client = TJUClient(settings)
    if not client.configured:
        print("未配置 TJU_API_KEY。请在项目根目录 .env 文件中填写 API Key。")
        return 1

    registry = ToolRegistry(build_network_tools(settings), retriever)
    agent = AgentOrchestrator(
        client,
        registry,
        max_tool_rounds=settings.max_tool_rounds,
    )
    try:
        result = agent.run(
            "天津大学 VPN 怎么使用？请先调用 knowledge_search 检索本地知识库，"
            "只依据检索结果回答，并明确标出资料类型、标题和原始 URL。"
        )
    finally:
        client.close()

    print(f"状态：{result.status.value}，工具轮次：{result.tool_rounds}")
    for step in result.steps:
        print(f"[{step.round}] {step.tool_name} ({step.tool_call_id}) -> {step.result.summary}")
    print("\n最终回答：")
    print(result.answer)
    print("\n结构化来源：")
    for source in result.sources:
        print(
            f"- [{source.source_type.value}] {source.title} | "
            f"{source.source} | score={source.score:.3f}"
        )
    if settings.tju_show_token_usage:
        print(f"Token 用量：{result.usage.total_tokens}")

    if result.status is not AgentStatus.COMPLETED:
        print("验收失败：Agent 未完成知识问答。")
        return 1
    if "knowledge_search" not in {step.tool_name for step in result.steps}:
        print("验收失败：模型没有调用 knowledge_search。")
        return 1
    if not result.sources:
        print("验收失败：回答没有结构化知识来源。")
        return 1
    if not any(source.source in result.answer for source in result.sources):
        print("验收失败：最终回答没有引用原始 URL。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
