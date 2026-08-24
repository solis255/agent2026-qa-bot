#!/usr/bin/env python3
"""Safely verify the TJU Competition OpenAI-compatible API configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://ai.tju.edu.cn/api/agent2026/agent2026-netpilot"
DEFAULT_MODEL = "tju-llm"


def main() -> int:
    """Send one small request without logging or displaying the API Key."""
    load_dotenv(REPO_ROOT / ".env")

    api_key = os.getenv("TJU_API_KEY", "").strip()
    base_url = os.getenv("TJU_API_BASE", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.getenv("TJU_MODEL", DEFAULT_MODEL).strip()

    if not api_key:
        print("未配置 TJU_API_KEY。请在项目根目录 .env 文件中填写 API Key。")
        return 1

    if base_url.endswith("/chat/completions"):
        print("TJU_API_BASE 不应包含 /chat/completions；OpenAI SDK 会自动添加该路径。")
        return 1

    try:
        from openai import (
            APIConnectionError,
            APIStatusError,
            AuthenticationError,
            OpenAI,
            RateLimitError,
        )
    except ModuleNotFoundError:
        print("缺少 openai SDK。请先运行：python -m pip install -r requirements.txt")
        return 1

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30.0,
        max_retries=2,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个简洁的 API 连通性测试助手。"},
                {"role": "user", "content": "请只回复：TJU API 连接成功"},
            ],
            temperature=0.0,
            max_tokens=30,
        )
    except AuthenticationError:
        print("认证失败（HTTP 401）：请检查 .env 中的 TJU_API_KEY。")
        return 1
    except RateLimitError:
        print("请求过于频繁（HTTP 429）：请稍后重试。")
        return 1
    except APIConnectionError as exc:
        print(f"无法连接 TJU API：{exc}")
        return 1
    except APIStatusError as exc:
        print(f"TJU API 返回 HTTP {exc.status_code}，请稍后重试或检查专属端点。")
        return 1

    content = response.choices[0].message.content or ""
    print(f"模型回复：{content.strip()}")
    if response.usage:
        print(f"Token 用量：{response.usage.total_tokens}")
    print(f"已通过专属地址调用模型：{model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
