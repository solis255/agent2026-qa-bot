"""Deterministic diagnosis reports and bounded export artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from netpilot.models import DiagnosisRecordView, DiagnosisReportView


ReportFormat = Literal["markdown", "json"]
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

TOOL_LABELS = {
    "get_network_info": "网络接口",
    "ping_host": "Ping 可达性",
    "dns_lookup": "DNS 解析",
    "tcp_check": "TCP 端口",
    "http_check": "HTTP 访问",
    "traceroute": "路由追踪",
    "knowledge_search": "校园网络知识检索",
}
STATUS_LABELS = {
    "normal": "正常",
    "abnormal": "发现异常",
    "error": "执行失败",
    "inconclusive": "结果不确定",
    "blocked": "安全阻止",
    "reference": "参考资料",
}
CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低"}
ISSUE_LABELS = {
    "undetermined": "尚未确定",
    "no_issue_observed": "未发现异常",
    "insufficient_evidence": "证据不足",
    "dns_resolution_failure": "DNS 解析故障",
    "local_network_configuration": "本地网络配置",
    "icmp_unreachable": "ICMP 不可达",
    "tcp_connectivity_failure": "TCP 连接故障",
    "http_connectivity_failure": "HTTP 访问故障",
    "proxy_fake_ip_mapping": "代理 Fake-IP 映射",
}


class DiagnosisReportTooLargeError(RuntimeError):
    """Raised when an export exceeds the configured response limit."""


@dataclass(frozen=True)
class DiagnosisReportArtifact:
    content: bytes
    media_type: str
    filename: str


def build_diagnosis_report(record: DiagnosisRecordView) -> DiagnosisReportView:
    """Build a stable report directly from one immutable diagnosis snapshot."""

    return DiagnosisReportView(
        report_id=record.record_id,
        record_id=record.record_id,
        session_id=record.session_id,
        generated_at=record.created_at,
        question=record.user_message,
        conclusion=record.answer,
        diagnosis=record.diagnosis,
        metrics=record.metrics,
        tool_calls=record.tool_calls,
        sources=record.sources,
    )


def export_diagnosis_report(
    report: DiagnosisReportView,
    report_format: ReportFormat,
    *,
    max_bytes: int = 1_000_000,
) -> DiagnosisReportArtifact:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if report_format == "markdown":
        content = render_report_markdown(report).encode("utf-8")
        extension = "md"
        media_type = "text/markdown; charset=utf-8"
    elif report_format == "json":
        content = render_report_json(report).encode("utf-8")
        extension = "json"
        media_type = "application/json; charset=utf-8"
    else:
        raise ValueError("unsupported report format")
    if len(content) > max_bytes:
        raise DiagnosisReportTooLargeError("诊断报告超过允许的导出大小")
    return DiagnosisReportArtifact(
        content=content,
        media_type=media_type,
        filename=f"netpilot-diagnosis-{report.record_id}.{extension}",
    )


def render_report_json(report: DiagnosisReportView) -> str:
    payload = report.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_report_markdown(report: DiagnosisReportView) -> str:
    diagnosis = report.diagnosis
    usage = report.metrics.token_usage
    lines = [
        "# TJU NetPilot 故障诊断报告",
        "",
        "## 报告信息",
        "",
        f"- 报告 ID：`{report.report_id}`",
        f"- 诊断记录 ID：`{report.record_id}`",
        f"- 会话 ID：`{report.session_id}`",
        f"- 生成时间：{_markdown_text(report.generated_at.isoformat())}",
        f"- Agent 状态：{_markdown_text(str(getattr(diagnosis.status, 'value', diagnosis.status)))}",
        f"- 主要问题：{_markdown_text(ISSUE_LABELS.get(diagnosis.primary_issue, diagnosis.primary_issue))}",
        f"- 置信度：{_markdown_text(CONFIDENCE_LABELS.get(diagnosis.confidence, diagnosis.confidence))}",
        "",
        "## 用户问题",
        "",
        *_blockquote(report.question),
        "",
        "## 诊断结论",
        "",
        _markdown_text(report.conclusion),
        "",
        "## 执行指标",
        "",
        f"- Prompt Token：{usage.prompt_tokens}",
        f"- Completion Token：{usage.completion_tokens}",
        f"- Total Token：{usage.total_tokens}",
        f"- LLM 总耗时：{report.metrics.llm_duration_ms:.2f} ms",
        f"- Tool 总耗时：{report.metrics.tool_duration_ms} ms",
        f"- Tool 调用次数：{report.metrics.tool_calls}",
        "",
        "## 检测证据",
        "",
    ]
    if not report.tool_calls:
        lines.append("- 本次诊断没有调用网络或知识工具。")
    for index, tool in enumerate(report.tool_calls, start=1):
        label = TOOL_LABELS.get(tool.tool_name, tool.tool_name)
        status = STATUS_LABELS.get(tool.finding_status, tool.finding_status)
        lines.extend(
            [
                f"### {index}. {_markdown_text(label)}",
                "",
                f"- 状态：{_markdown_text(status)}",
                f"- 执行轮次：{tool.round}",
                f"- 执行成功：{'是' if tool.success else '否'}",
                f"- 耗时：{tool.duration_ms} ms",
                f"- 摘要：{_markdown_text(tool.summary)}",
                f"- 错误码：{_markdown_text(tool.error_code or '无')}",
                "- 参数：",
                "",
                *_indented_json(tool.arguments),
                "",
                "- 结构化结果：",
                "",
                *_indented_json(tool.data),
                "",
            ]
        )

    lines.extend(["## 建议操作", ""])
    if diagnosis.recommendations:
        lines.extend(
            f"- {_markdown_text(item)}" for item in diagnosis.recommendations
        )
    else:
        lines.append("- 本次诊断没有生成额外建议。")

    lines.extend(["", "## 结论限制", ""])
    if diagnosis.limitations:
        lines.extend(f"- {_markdown_text(item)}" for item in diagnosis.limitations)
    else:
        lines.append("- 本次诊断没有记录额外限制。")

    lines.extend(["", "## 参考知识", ""])
    if report.sources:
        for source in report.sources:
            lines.append(
                "- "
                f"{_markdown_text(source.title)} "
                f"（{_markdown_text(str(getattr(source.source_type, 'value', source.source_type)))}，"
                f"相关度 {source.score:.3f}）— {_safe_source(source.source)}"
            )
    else:
        lines.append("- 本次报告没有使用知识库来源。")

    lines.extend(
        [
            "",
            "---",
            "",
            "本报告由 TJU NetPilot 根据已保存的结构化诊断证据自动生成，未额外调用语言模型。",
            "",
        ]
    )
    return "\n".join(lines)


def _markdown_text(value: object) -> str:
    text = _CONTROL_CHARACTERS.sub("", str(value))
    replacements = {
        "\\": "\\\\",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "[": "\\[",
        "]": "\\]",
        "<": "&lt;",
        ">": "&gt;",
        "#": "\\#",
        "|": "\\|",
    }
    return "".join(replacements.get(character, character) for character in text)


def _blockquote(value: str) -> list[str]:
    lines = _CONTROL_CHARACTERS.sub("", value).splitlines() or [""]
    return [f"> {_markdown_text(line)}" for line in lines]


def _indented_json(value: object) -> list[str]:
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return [f"    {line}" for line in serialized.splitlines()]


def _safe_source(value: str) -> str:
    cleaned = _CONTROL_CHARACTERS.sub("", value).strip()
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "来源链接不可用"
    return f"<{cleaned.replace('<', '%3C').replace('>', '%3E')}>"
