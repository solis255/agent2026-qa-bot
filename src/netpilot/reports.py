"""Deterministic diagnosis reports and bounded export artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from netpilot.models import DiagnosisRecordView, DiagnosisReportView
from netpilot.privacy import export_safe, sanitize_url
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
    "single_service": "单一服务访问异常（不代表全局断网）",
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

    record = export_safe(record)
    target = record.diagnostic_target
    superseded_ids = {e.evidence_id for e in record.verification_evidence if e.superseded}
    current_calls = [call for call in record.tool_calls if call.evidence_id not in superseded_ids
                     and (target.subject == "unknown" or matches_target(call, target))]
    archived_calls = [call for call in record.tool_calls if call not in current_calls]
    conclusion = record.answer
    if record.conversation_turns and target.subject != "unknown":
        last_turn = record.conversation_turns[-1]
        if (last_turn.target_subject, last_turn.target_version) != (target.subject, target.target_version):
            conclusion = "诊断对象已切换，尚无当前对象的直接检测结论；其他对象观察只保留于历史。"
    from netpilot.client_snapshot.schemas import refresh_summary
    summary = refresh_summary(record.client_snapshot_summary)
    if summary:
        summary.applicable = summary.applicable and target.subject == "user_client" and summary.target_version == target.target_version
        if summary.applicable and summary.snapshot_id == record.analyzed_snapshot_id:
            conclusion = record.diagnosis.summary
    if summary and summary.applicable and summary.snapshot_id != record.analyzed_snapshot_id:
        conclusion = "客户端快照已更新，尚待分析；旧快照结论不代表当前状态。"
    if summary and summary.applicable and (summary.stale or summary.clock_skew_suspected):
        conclusion = "快照已过期或疑似时钟偏差；以下仅为历史采集状态，不代表现在。\n\n" + conclusion
    return DiagnosisReportView(
        context_acquisition=record.context_acquisition,
        is_demo=record.is_demo, demo_scenario_id=record.demo_scenario_id, data_notice=record.data_notice,
        privacy_metadata=record.privacy_metadata,
        privacy_policy_version=record.privacy_policy_version,
        report_id=record.record_id,
        record_id=record.record_id,
        session_id=record.session_id,
        environment_profile=record.environment_profile,
        diagnostic_target=target,
        client_snapshot_summary=summary,
        client_evidence=record.client_evidence,
        remediation_plan=record.remediation_plan,
        resolution=record.resolution,resolution_transitions=record.resolution_transitions,
        escalation_packages=record.escalation_packages,
        verification_cycles=record.verification_cycles,
        verification_evidence=record.verification_evidence,
        remediation_plan_history=record.remediation_plan_history,
        remediation_readiness=record.remediation_readiness,
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
    payload = export_safe(report).model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_report_markdown(report: DiagnosisReportView) -> str:
    report = export_safe(report)
    diagnosis = report.diagnosis
    usage = report.metrics.token_usage
    lines = [
        "# TJU NetPilot 故障诊断报告",
        "",
        "## 报告信息",
        "",
        f"- 报告 ID：`{report.report_id}`",
        f"- 隐私策略版本：{report.privacy_policy_version}（凭据移除、设备标识最小化）",
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
    if report.client_snapshot_summary:
        snapshot = report.client_snapshot_summary
        lines.extend([
            "## 客户端诊断快照", "",
            f"- 快照：{snapshot.snapshot_id} / 序号 {snapshot.snapshot_sequence}",
            f"- 采集时间：{snapshot.generated_at.isoformat()}",
            f"- 时效：{'已过期（历史）' if snapshot.stale else '疑似时钟偏差' if snapshot.clock_skew_suspected else '采集时点证据'}",
            f"- 系统：Windows {_markdown_text(snapshot.os.version or '版本未知')}",
            "- 来源：用户主动上传，未签名；非实时检测、非远程执行，不增加 Tool 调用次数。", "",
        ])
        from netpilot.client_snapshot.service import snapshot_answer
        current_client = [item for item in report.client_evidence if not item.superseded and matches_target(item, report.diagnostic_target)]
        if current_client:
            lines.extend([_markdown_text(snapshot_answer(current_client, "report_request")), ""])
        for item in report.client_evidence:
            archived = item.superseded or not matches_target(item, report.diagnostic_target)
            lines.append(f"- {'历史归档（不用于当前结论）' if archived else '采集证据'} / user_client v{item.target_version} / {_markdown_text(item.tool_name)} / {item.observed_at.isoformat()}：{_markdown_text(item.summary)}")
        lines.extend(["", "## 网络与知识 Tool 调用", ""])
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

    lines.extend(["", "## 修复计划", ""])
    if report.remediation_plan:
        plan=report.remediation_plan
        lines.extend([f"- 版本：{plan.plan_version}；对象：{plan.target_subject} v{plan.target_version}",
                      f"- 状态：{plan.status}；就绪度：{plan.readiness}；{_markdown_text(plan.readiness_reason)}",
                      "- 仅为手动计划。completed 仅代表流程结束，不代表网络故障已解决。",""])
        for step in plan.steps:
            lines.extend([f"### Step {step.order} — {_markdown_text(step.title)}", "",
                f"- 风险：{step.risk}；管理员：{'是' if step.requires_admin else '否'}",
                f"- 状态：{step.status}；用户反馈：{step.outcome}",f"- 理由：{_markdown_text(step.rationale)}",
                *[f"- 操作：{_markdown_text(item)}" for item in step.instructions],
                f"- 验证：{_markdown_text(step.verification)}",
                *[f"- 回滚：{_markdown_text(item)}" for item in step.rollback_instructions],
                f"- 停止条件：{_markdown_text(step.continue_condition or '用户自行决定停止')}",
                f"- Evidence：{_markdown_text(', '.join(step.evidence_ids) or '有限现象，无直接证据')}",
                f"- 来源标识：{_markdown_text(', '.join(step.source_refs) or '通用步骤，不依赖校园特定资料')}",
                f"- 用户备注：{_markdown_text(step.user_note or '无')}",""])
        for source in plan.sources:
            if source.source_ref in {ref for step in plan.steps for ref in step.source_refs}:
                lines.append(f"- {_markdown_text(source.source_type)} / {_markdown_text(source.title)} — {_safe_source(source.source)}")
    else:
        lines.append("- 未保存结构化修复计划；不会从旧回答反推。")
    if report.remediation_plan_history:
        lines.extend(["", "### 历史失效计划（不可继续执行）", ""])
        lines.extend(f"- v{item.plan_version} / {item.target_subject} v{item.target_version} / {item.status}" for item in report.remediation_plan_history)
    from netpilot.resolution.models import STATE_LABELS
    resolution=report.resolution
    lines.extend(["", "## 最终处理状态", "",f"- 当前状态：{STATE_LABELS[resolution.state]}（状态版本 {resolution.state_version}）",
        f"- 诊断对象：{SUBJECT_LABELS[report.diagnostic_target.subject]} v{report.diagnostic_target.target_version}",
        f"- 客观验证：{resolution.objective_result}；用户确认（主观）：{resolution.user_confirmation}",
        f"- 状态原因：{_markdown_text(resolution.reason_summary or '尚在诊断')}",
        f"- 最后 Verification：{resolution.based_on_verification_id or '无'}",
        f"- 状态记录时间：{resolution.updated_at.isoformat()}；仅代表当时的闭环结论，不保证此后永不复发。",
        f"- 人工支持建议：{_markdown_text(resolution.escalation_summary or '无')}；未提交外部工单。",""])
    for audit in report.resolution_transitions:
        lines.append(f"- v{audit.state_version}：{STATE_LABELS[audit.from_state]} → {STATE_LABELS[audit.to_state]}；{_markdown_text(audit.summary)}")
    lines.extend(["", "## 修复前后验证", "", "Verification ≠ Resolution；有改善不代表故障已解决。", ""])
    for cycle in report.verification_cycles:
        labels = {"improved":"有改善","unchanged":"无变化","worsened":"变差","inconclusive":"暂时无法确认","unknown":"尚未验证"}
        step_names = {step.step_id:step.title for plan in [report.remediation_plan,*report.remediation_plan_history] if plan for step in plan.steps}
        lines.extend([f"### Verification {cycle.verification_sequence}", "",
            f"- 对象：{cycle.target_subject} v{cycle.target_version}；流程：{cycle.status}",
            f"- 修复计划：v{cycle.remediation_plan_version}；步骤：{_markdown_text('、'.join(step_names.get(s,str(s)) for s in cycle.remediation_step_ids) or '尚未执行')}",
            f"- Baseline task v{cycle.baseline.task_version} / After task v{cycle.after_task_version or '尚未开始'}",
            f"- 基线冻结时间：{cycle.baseline.captured_at.isoformat()}；After：{cycle.after.captured_at.isoformat() if cycle.after else '未采集'}",
            f"- Baseline Evidence：{', '.join(cycle.baseline.evidence_ids) or '无'}",
            f"- After Evidence：{', '.join(cycle.after.evidence_ids) if cycle.after else '等待采集'}", "",
            "| 指标 / 目标 | 修复前 | 修复后 | 变化 |", "|---|---|---|---|"])
        for check in cycle.checks:
            lines.append(f"| {_markdown_text(check.metric)} / {_markdown_text(check.target or '')} | {_markdown_text(check.baseline_value or '未知')} | {_markdown_text(check.after_value or '未采集')} | {_markdown_text(labels.get(check.change, check.change))} |")
        lines.extend(["",f"结果：**{labels[cycle.result]}**",_markdown_text(cycle.result_summary or ''), ""])
        if cycle.user_observation:
            lines.extend([f"用户主观反馈（非客观证据）：{cycle.user_observation.symptom_status}；{_markdown_text(cycle.user_observation.note or '')}",""])
    if not report.verification_cycles: lines.append("- 未保存验证；不会从旧回答反推。")
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
    if report.is_demo: lines.insert(2, "> **DEMO / 模拟数据 — 不可作为真实网络测量或实际报修依据。**")
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
    cleaned = sanitize_url(_CONTROL_CHARACTERS.sub("", value).strip())
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "来源链接不可用"
    return f"<{cleaned.replace('<', '%3C').replace('>', '%3E')}>"
