from __future__ import annotations

import pytest
from pydantic import ValidationError

from netpilot.config import MockScenario, Settings, ToolMode


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_settings_allow_an_unconfigured_llm(api_key: str | None) -> None:
    settings = Settings(_env_file=None, tju_api_key=api_key)

    assert settings.llm_configured is False


def test_settings_detect_a_configured_llm_without_exposing_the_key() -> None:
    api_key = "test-secret-that-must-not-leak"
    settings = Settings(_env_file=None, tju_api_key=api_key)

    assert settings.llm_configured is True
    assert api_key not in repr(settings)
    assert api_key not in settings.model_dump_json()


def test_settings_load_valid_operational_values() -> None:
    settings = Settings(
        _env_file=None,
        tool_mode="local",
        mock_scenario="partial_connectivity",
        network_timeout_seconds=10,
        app_port=9000,
    )

    assert settings.tool_mode is ToolMode.LOCAL
    assert settings.mock_scenario is MockScenario.PARTIAL_CONNECTIVITY
    assert settings.network_timeout_seconds == 10
    assert settings.app_port == 9000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tool_mode", "unsafe"),
        ("network_timeout_seconds", 0),
        ("network_timeout_seconds", 31),
        ("max_tool_rounds", 0),
        ("max_history_messages", 0),
        ("rag_top_k", 0),
        ("app_port", 70000),
        ("app_host", "  "),
    ],
)
def test_settings_reject_invalid_operational_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_tju_api_base_is_normalized() -> None:
    settings = Settings(
        _env_file=None,
        tju_api_base="https://ai.tju.edu.cn/api/agent2026/example/",
    )

    assert settings.tju_api_base == "https://ai.tju.edu.cn/api/agent2026/example"


@pytest.mark.parametrize(
    "base_url",
    [
        "not-a-url",
        "ftp://ai.tju.edu.cn/api/agent2026/example",
        "https://ai.tju.edu.cn/api/agent2026/example?debug=true",
        "https://ai.tju.edu.cn/api/agent2026/example/chat/completions",
    ],
)
def test_settings_reject_invalid_tju_api_bases(base_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, tju_api_base=base_url)
