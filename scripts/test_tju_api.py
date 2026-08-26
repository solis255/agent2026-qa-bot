#!/usr/bin/env python3
"""Safely verify the production NetPilot TJU client with one small request."""

from __future__ import annotations

import sys

from pydantic import ValidationError

from netpilot.config import Settings
from netpilot.llm import ChatMessage, TJUClient, TJUClientError


def _configure_windows_console() -> None:
    """Keep Chinese smoke-test output readable in Windows terminals."""

    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    """Send one small request without logging or displaying the API Key."""
    _configure_windows_console()
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"TJU 配置无效：{exc.error_count()} 个字段未通过校验。")
        return 1

    client = TJUClient(settings)
    if not client.configured:
        print("未配置 TJU_API_KEY。请在项目根目录 .env 文件中填写 API Key。")
        return 1

    try:
        result = client.chat(
            [
                ChatMessage(
                    role="system",
                    content="你是一个简洁的 API 连通性测试助手。",
                ),
                ChatMessage(role="user", content="请只回复：TJU API 连接成功"),
            ],
            temperature=0.0,
            max_tokens=30,
        )
    except TJUClientError as exc:
        suffix = f"（request_id={exc.request_id}）" if exc.request_id else ""
        print(f"{exc}{suffix}")
        return 1
    finally:
        client.close()

    print(f"模型回复：{result.content}")
    if settings.tju_show_token_usage:
        print(f"Token 用量：{result.usage.total_tokens}")
    print(f"模型：{result.model}，耗时：{result.duration_ms:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
