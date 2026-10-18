"""Deterministic diagnosis reports and bounded export artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from netpilot.models import DiagnosisRecordView, DiagnosisReportView
from netpilot.environment import OS_LABELS, ACCESS_LABELS, SCOPE_LABELS, bool_label
from netpilot.diagnostic_target import SUBJECT_LABELS, EXECUTION_LABELS, RELATIONSHIP_LABELS, matches_target


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
    """Build a stable report from one Session-level diagnosis snapshot."""

    target = record.diagnostic_target
    current_calls = [call for call in record.tool_calls if target.subject == "unknown" or matches_target(call, target)]
    archived_calls = [call for call in record.tool_calls if call not in current_calls]
    conclusion = record.answer
    if record.conversation_turns and target.subject != "unknown":
        last_turn = record.conversation_turns[-1]
        if (last_turn.target_subject, last_turn.target_version) != (target.subject, target.target_version):
            conclusion = "诊断对象已切换，尚无当前对象的直接检测结论；其他对象观察只保留于历史。"
    return DiagnosisReportView(
        report_id=record.record_id,
        record_id=record.record_id,
        session_id=record.session_id,
        environment_profile=record.environment_profile,
        diagnostic_target=target,
        generated_at=record.updated_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        turn_count=record.turn_count,
        question=record.user_message,
        latest_user_message=record.latest_user_message,
        conclusion=conclusion,
        diagnosis=record.diagnosis,
        metrics=record.metrics,
        tool_calls=current_calls,
        archived_tool_calls=archived_calls,
        sources=record.sources,
        conversation_turns=record.conversation_turns,
        conversation_complete=record.conversation_complete,
        reasoning_trace=record.reasoning_trace,
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
        f"- 会话创建时间：{_markdown_text(report.created_at.isoformat())}",
        f"- 最近更新时间：{_markdown_text(report.updated_at.isoformat())}",
        f"- 成功完成 Turn：{report.turn_count}",
        f"- 报告快照时间：{_markdown_text(report.generated_at.isoformat())}",
        f"- Agent 状态：{_markdown_text(str(getattr(diagnosis.status, 'value', diagnosis.status)))}",
        f"- 主要问题：{_markdown_text(ISSUE_LABELS.get(diagnosis.primary_issue, diagnosis.primary_issue))}",
        f"- 置信度：{_markdown_text(CONFIDENCE_LABELS.get(diagnosis.confidence, diagnosis.confidence))}",
        "",
        "## 用户问题",
        "",
        *_blockquote(report.question),
        "",
        "## 用户环境",
        "",
        f"- 设备系统：{OS_LABELS[report.environment_profile.os_family]}",
        f"- 网络接入：{ACCESS_LABELS[report.environment_profile.network_access]}",
        f"- VPN：{bool_label(report.environment_profile.vpn_enabled)}",
        f"- Proxy：{bool_label(report.environment_profile.proxy_enabled)}",
        f"- 影响范围：{SCOPE_LABELS[report.environment_profile.affected_scope]}",
        f"- 受影响服务：{_markdown_text(report.environment_profile.affected_service or '未知')}",
        f"- 客户端模式：{report.environment_profile.client_mode}",
        "- 环境上下文不是实时网络检测证据；未知不等于关闭。Local 仅检测运行 NetPilot 的主机。",
        "",
        "## 诊断对象",
        "",
        f"- 对象：{SUBJECT_LABELS[report.diagnostic_target.subject]}",
        f"- 对象版本：{report.diagnostic_target.target_version}",
        f"- 与 NetPilot 关系：{RELATIONSHIP_LABELS[report.diagnostic_target.relationship_to_netpilot]}",
        f"- 工具执行位置：{EXECUTION_LABELS[report.diagnostic_target.execution_context]}",
        f"- 直接检测能力：{'模拟可用' if report.diagnostic_target.subject == 'mock_client' and report.diagnostic_target.limitation_code == 'none' else '可用' if report.diagnostic_target.limitation_code == 'none' else '受限 / 未记录'}",
        "- 仅当前对象/版本的网络证据用于当前结论；知识资料不属于设备检测。",
        "",
        "## 最近一轮用户消息",
        "",
        *_blockquote(report.latest_user_message),
        "",
        "## 诊断结论",
        "",
        _markdown_text(report.conclusion),
        "",
        "## 执行指标",
        "",
        "以下为 Session 累计指标，包含历史对象；不代表当前对象执行了这些检测。",
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
                f"- 诊断对象：{SUBJECT_LABELS[tool.target_subject]} v{tool.target_version}",
                f"- 执行位置：{EXECUTION_LABELS[tool.execution_context] if tool.execution_scope != 'target_neutral' else '对象无关的知识检索'}",
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

    if report.archived_tool_calls:
        lines.extend(["## 其他对象的历史检测（不用于当前结论）", ""])
        for tool in report.archived_tool_calls:
            lines.append(f"- {SUBJECT_LABELS[tool.target_subject]} v{tool.target_version} / {EXECUTION_LABELS[tool.execution_context]} / {_markdown_text(tool.tool_name)}：{_markdown_text(tool.summary)}")
        lines.append("")
    lines.extend(["## 诊断思路", "", "以下保留 Session 的建立/切换及历史决策，其他对象观察不支持当前对象结论。", ""])
    if report.reasoning_trace:
        for index, step in enumerate(report.reasoning_trace, 1):
            lines.append(f"{index}. **{_markdown_text(step.title)}**：{_markdown_text(step.summary)}")
    else:
        lines.append("- 本记录没有保存诊断思路；不会根据旧答案推造决策轨迹。")

    lines.extend(["", "## 建议操作", ""])
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

    lines.extend(["", "## 会话记录", ""])
    if not report.conversation_complete:
        lines.extend([
            "该记录创建于完整会话持久化功能启用之前，仅保留部分对话内容。",
            "",
        ])
    for turn in report.conversation_turns:
        lines.extend([
            f"### Turn {turn.turn_index}", "",
            f"诊断对象：{SUBJECT_LABELS[turn.target_subject]} v{turn.target_version}", "",
            "用户：", "", *_blockquote(turn.user_message), "",
            "诊断助手：", "", _markdown_text(turn.assistant_answer), "",
        ])

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
