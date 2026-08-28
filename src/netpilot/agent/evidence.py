"""Shared interpretation of tool execution results and diagnostic findings."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


NEGATIVE_FIELDS = {
    "ping_host": "reachable",
    "dns_lookup": "resolved",
    "tcp_check": "connected",
    "http_check": "reachable",
    "traceroute": "reached_destination",
}


def json_data(data: Any) -> Any:
    """Return JSON-compatible evidence without changing the stored result."""

    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    return data


def finding_status(
    tool_name: str,
    success: bool,
    data: Any,
    error_code: str | None = None,
) -> str:
    """Separate execution failures from valid negative network observations."""

    if not success and error_code == "security_blocked":
        return "blocked"
    if not success and error_code in {"timeout", "unsupported"}:
        return "inconclusive"
    if not success:
        return "error"
    if tool_name == "knowledge_search":
        return "reference"
    if not isinstance(data, dict):
        return "normal"
    if tool_name == "get_network_info":
        configured = data.get("ipv4") and data.get("default_gateway")
        return "normal" if configured else "abnormal"
    if tool_name == "http_check":
        if data.get("reachable") is False:
            return "abnormal"
        status_code = data.get("status_code")
        if isinstance(status_code, int) and status_code >= 400:
            return "abnormal"
        return "normal"
    field = NEGATIVE_FIELDS.get(tool_name)
    if field is not None and data.get(field) is False:
        return "abnormal"
    return "normal"


def llm_tool_feedback(tool_name: str, result: Any) -> dict[str, Any]:
    """Build compact tool feedback that upstream services cannot misread as failure.

    Some OpenAI-compatible gateways treat any nested JSON ``false`` value as a
    failed function call.  NetPilot instead sends an explicit execution state
    and diagnostic finding, while preserving exact typed evidence in its own
    Agent result and Web API response.
    """

    data = json_data(result.data)
    error_code = None
    if result.error is not None:
        error_code = str(getattr(result.error.code, "value", result.error.code))
    status = finding_status(tool_name, result.success, data, error_code)
    if result.error is not None:
        return {
            "tool": tool_name,
            "execution_status": "error",
            "diagnostic_status": "tool_error",
            "summary": result.summary,
            "evidence": _replace_booleans(data),
            "error": {
                "code": str(
                    getattr(result.error.code, "value", result.error.code)
                ),
                "message": result.error.message,
            },
        }
    summary = result.summary
    if status == "abnormal":
        summary = (
            "检测执行成功并已产生有效的异常观察。"
            "该结果可直接用于诊断，请勿用相同目标重复检测。"
        )
    return {
        "tool": tool_name,
        "execution_status": "success",
        "diagnostic_status": {
            "normal": "healthy_observation",
            "abnormal": "issue_observed",
            "reference": "reference_found",
        }.get(status, status),
        "summary": summary,
        "evidence": _replace_booleans(data),
    }


def _replace_booleans(value: Any) -> Any:
    """Use unambiguous words rather than booleans in model-facing feedback."""

    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return {key: _replace_booleans(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_booleans(item) for item in value]
    return value
