#!/usr/bin/env python3
"""Validate the Windows/Python lab setup without consuming API tokens."""

import sys
from pathlib import Path

from tju_llm_client import TJUAPIError, get_settings


def print_header(text: str) -> None:
    print(f"\n{'=' * 70}\n  {text}\n{'=' * 70}\n")


def check_python() -> bool:
    print_header("Python Version Check")
    version = sys.version_info
    ok = version >= (3, 10)
    print(f"{'✅' if ok else '❌'} Python {version.major}.{version.minor}.{version.micro}")
    if not ok:
        print("   Python 3.10 or newer is required.")
    return ok


def check_tju_configuration() -> bool:
    """Validate names and endpoint only; never display the API Key."""
    print_header("TJU API Configuration Check")
    try:
        _api_key, base_url, model = get_settings()
    except TJUAPIError as exc:
        print(f"❌ {exc}")
        return False
    print("✅ TJU_API_KEY is configured (value hidden)")
    print(f"✅ TJU_API_BASE: {base_url}")
    print(f"✅ TJU_MODEL: {model}")
    print("ℹ️  No network request was sent; run scripts/test_tju_api.py for a live test.")
    return True


def check_labs() -> bool:
    print_header("Lab Files Check")
    repo_root = Path(__file__).resolve().parents[1]
    labs = [
        "labs/lab1-ollama/simple_ollama_test.py",
        "labs/lab2-prompts/prompt_engineering_race.py",
        "labs/lab3-chatbot/chatbot_v2_with_memory.py",
        "labs/lab4-agentic/agentic_network_bot.py",
        "labs/lab5-mcp/client_test.py",
        "labs/lab6-production-readiness/safe_tools.py",
    ]
    all_ok = True
    for lab in labs:
        exists = (repo_root / lab).exists()
        print(f"{'✅' if exists else '❌'} {lab}")
        all_ok &= exists
    return all_ok


def main() -> int:
    print("\nBuilding AI Agents for Network Operations - Setup Test".center(70))
    checks = [check_python(), check_tju_configuration(), check_labs()]
    print_header("Summary")
    if all(checks):
        print("✅ All checks passed. Next:")
        print("   python labs/lab1-ollama/simple_ollama_test.py")
        return 0
    print("❌ Some checks failed; fix the items above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
