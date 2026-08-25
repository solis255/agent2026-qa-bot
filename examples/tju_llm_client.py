#!/usr/bin/env python3
"""Shared client for the TJU Competition OpenAI-compatible API.

All migrated labs use this module so credentials, endpoint validation, retry
limits, error messages, tool-call conversion, and token reporting remain
consistent. The API Key is read only from ``.env`` or the process environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://ai.tju.edu.cn/api/agent2026/agent2026-netpilot"
DEFAULT_MODEL = "tju-llm"


def _configure_windows_console() -> None:
    """Allow the teaching scripts' Chinese text and emoji on Windows consoles."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


_configure_windows_console()


class TJUAPIError(RuntimeError):
    """A safe, user-facing error raised for configuration or API failures."""


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> tuple[str, str, str]:
    """Load and validate API Key, SDK base URL, and model from the environment."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("TJU_API_KEY", "").strip()
    base_url = os.getenv("TJU_API_BASE", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.getenv("TJU_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    if not api_key:
        raise TJUAPIError("未配置 TJU_API_KEY，请在项目根目录 .env 文件中填写。")
    if base_url.endswith("/chat/completions"):
        raise TJUAPIError(
            "TJU_API_BASE 不应包含 /chat/completions；OpenAI SDK 会自动添加该路径。"
        )
    if not base_url.startswith("https://ai.tju.edu.cn/api/agent2026/"):
        raise TJUAPIError("TJU_API_BASE 必须使用智能体广场提供的比赛专属地址。")
    return api_key, base_url, model


def create_client(timeout: float = 60.0) -> tuple[OpenAI, str]:
    """Create a bounded-retry client and return it with the configured model."""
    api_key, base_url, model = get_settings()
    return (
        OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=2,
        ),
        model,
    )


def _report_usage(response: Any) -> None:
    if not _env_flag("TJU_SHOW_TOKEN_USAGE", default=True):
        return
    usage = getattr(response, "usage", None)
    total = getattr(usage, "total_tokens", None)
    if total is not None:
        print(f"[TJU API] Token 用量: {total}")


def _raise_api_error(exc: Exception) -> None:
    if isinstance(exc, AuthenticationError):
        raise TJUAPIError("TJU API 认证失败（401），请检查 .env 中的 TJU_API_KEY。") from exc
    if isinstance(exc, RateLimitError):
        raise TJUAPIError("TJU API 触发速率限制（429），请稍后重试。") from exc
    if isinstance(exc, APITimeoutError):
        raise TJUAPIError("TJU API 请求超时。") from exc
    if isinstance(exc, APIConnectionError):
        raise TJUAPIError("无法连接 TJU API，请检查网络和专属地址。") from exc
    if isinstance(exc, APIStatusError):
        raise TJUAPIError(f"TJU API 返回 HTTP {exc.status_code}。") from exc
    raise TJUAPIError(f"TJU API 调用失败：{exc}") from exc


def generate_text_result(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    model: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Generate text and return a small, provider-neutral response dictionary."""
    client, configured_model = create_client(timeout=timeout)
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=model or configured_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
    except Exception as exc:
        _raise_api_error(exc)

    _report_usage(response)
    usage = response.usage
    return {
        "response": (response.choices[0].message.content or "").strip(),
        "model": response.model or model or configured_model,
        "tokens": {
            "prompt": getattr(usage, "prompt_tokens", 0) or 0,
            "response": getattr(usage, "completion_tokens", 0) or 0,
            "total": getattr(usage, "total_tokens", 0) or 0,
        },
    }


def generate_text(
    prompt: str,
    *,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    model: Optional[str] = None,
    timeout: float = 60.0,
) -> str:
    """Generate one non-streaming text response through Chat Completions."""
    result = generate_text_result(
        prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        timeout=timeout,
    )
    return str(result["response"])


def chat_message(
    messages: List[Dict[str, Any]],
    *,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    model: Optional[str] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Return an assistant message dict, including native function calls."""
    client, configured_model = create_client(timeout=timeout)
    request: Dict[str, Any] = {
        "model": model or configured_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        request["tools"] = tools
        request["tool_choice"] = tool_choice or "auto"

    try:
        response = client.chat.completions.create(**request)
    except Exception as exc:
        _raise_api_error(exc)

    _report_usage(response)
    message = response.choices[0].message
    result: Dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in message.tool_calls
        ]
    return result
