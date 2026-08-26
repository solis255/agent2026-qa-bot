from __future__ import annotations

from typing import Any

import pytest

from netpilot.agent import ToolRegistry
from netpilot.config import Settings
from netpilot.tools import build_network_tools
from netpilot.tools.schemas import ToolErrorCode


EXPECTED_TOOLS = {
    "get_network_info",
    "ping_host",
    "dns_lookup",
    "tcp_check",
    "http_check",
    "traceroute",
}


def build_registry(scenario: str = "healthy") -> ToolRegistry:
    settings = Settings(
        _env_file=None,
        tool_mode="mock",
        mock_scenario=scenario,
    )
    return ToolRegistry(build_network_tools(settings))


def test_registry_exposes_only_six_strict_read_only_tools() -> None:
    registry = build_registry()

    assert set(registry.names) == EXPECTED_TOOLS
    schemas = registry.schemas()
    assert {item["function"]["name"] for item in schemas} == EXPECTED_TOOLS
    assert "set_mock_scenario" not in str(schemas)

    for item in schemas:
        function = item["function"]
        parameters = function["parameters"]
        assert item["type"] == "function"
        assert function["strict"] is True
        assert parameters["additionalProperties"] is False
        assert set(parameters["required"]) == set(parameters["properties"])
        assert "default" not in str(parameters)


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("get_network_info", "{}"),
        ("ping_host", '{"host":"1.1.1.1","count":1}'),
        ("dns_lookup", '{"domain":"github.com"}'),
        ("tcp_check", '{"host":"github.com","port":443,"timeout":1}'),
        ("http_check", '{"url":"https://github.com"}'),
        ("traceroute", '{"host":"1.1.1.1","max_hops":3}'),
    ],
)
def test_registry_dispatches_every_allowlisted_tool(
    tool_name: str,
    arguments: str,
) -> None:
    execution = build_registry().execute(tool_name, arguments)

    assert execution.result.success is True
    assert execution.result.tool == tool_name


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_code"),
    [
        ("unknown_tool", "{}", ToolErrorCode.UNSUPPORTED),
        ("ping_host", "not-json", ToolErrorCode.INVALID_INPUT),
        ("ping_host", "[]", ToolErrorCode.INVALID_INPUT),
        (
            "ping_host",
            '{"host":"1.1.1.1","count":1,"command":"whoami"}',
            ToolErrorCode.INVALID_INPUT,
        ),
        (
            "tcp_check",
            '{"host":"github.com","port":70000,"timeout":1}',
            ToolErrorCode.INVALID_INPUT,
        ),
    ],
)
def test_registry_converts_untrusted_calls_to_safe_failures(
    tool_name: str,
    arguments: str,
    expected_code: ToolErrorCode,
) -> None:
    execution = build_registry().execute(tool_name, arguments)

    assert execution.result.success is False
    assert execution.result.data is None
    assert execution.result.error is not None
    assert execution.result.error.code == expected_code
    assert "whoami" not in execution.result.summary


def test_registry_returns_only_validated_normalized_arguments() -> None:
    execution = build_registry().execute(
        "ping_host",
        '{"host":"EXAMPLE.COM","count":2}',
    )

    assert execution.arguments == {"host": "example.com", "count": 2}
