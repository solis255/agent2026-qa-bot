import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples import tju_llm_client  # noqa: E402


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("TJU_API_KEY", raising=False)
    monkeypatch.setattr(tju_llm_client, "load_dotenv", lambda *_args, **_kwargs: None)

    with pytest.raises(tju_llm_client.TJUAPIError, match="TJU_API_KEY"):
        tju_llm_client.get_settings()


def test_rejects_full_completion_url(monkeypatch):
    monkeypatch.setenv("TJU_API_KEY", "test-only-key")
    monkeypatch.setenv(
        "TJU_API_BASE",
        "https://ai.tju.edu.cn/api/agent2026/agent2026-netpilot/chat/completions",
    )
    monkeypatch.setattr(tju_llm_client, "load_dotenv", lambda *_args, **_kwargs: None)

    with pytest.raises(tju_llm_client.TJUAPIError, match="不应包含"):
        tju_llm_client.get_settings()


def test_accepts_competition_sdk_base_url(monkeypatch):
    monkeypatch.setenv("TJU_API_KEY", "test-only-key")
    monkeypatch.setenv(
        "TJU_API_BASE",
        "https://ai.tju.edu.cn/api/agent2026/agent2026-netpilot",
    )
    monkeypatch.setenv("TJU_MODEL", "tju-llm")
    monkeypatch.setattr(tju_llm_client, "load_dotenv", lambda *_args, **_kwargs: None)

    _key, base_url, model = tju_llm_client.get_settings()
    assert base_url.endswith("/agent2026-netpilot")
    assert model == "tju-llm"
