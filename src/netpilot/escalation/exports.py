"""Bounded self-contained Markdown / exact-schema JSON, never transcript export."""
from netpilot.escalation.builder import package_digest
from netpilot.reports import DiagnosisReportArtifact, DiagnosisReportTooLargeError, _markdown_text
from netpilot.escalation.privacy import safe_package


def markdown(package):
    p = safe_package(package)
    text = lambda v: _markdown_text(str(v)) if v is not None else "未知 / 未记录"
    lines = ["# TJU NetPilot 升级报修材料", "", "仅供用户自行交接；未提交工单、未通知或发送给任何外部运维系统。", "",
        "## 1. 基本信息", f"- 材料 ID：{p.package_id}；版本：v{p.package_version}", f"- Session：{p.session_id}；生成时间：{p.generated_at.isoformat()}",
        f"- 诊断对象：{text(p.target.subject)} / {text(p.target.relationship_to_netpilot)} / {text(p.target.execution_context)}；对象版本 {p.target.target_version}",
        f"- {text(p.target.notice)}", f"- Digest (SHA-256)：{p.package_digest}", "", "## 2. 环境",
        *[f"- {key}：{text(value)}" for key,value in p.environment.model_dump().items()], "", "## 3. 问题",
        f"- 初始症状：{text(p.issue.original_symptom)}", f"- 当前症状：{text(p.issue.current_symptom)}", f"- primary_issue：{text(p.issue.primary_issue)}",
        f"- 起始：{text(p.issue.started_at)}；最近观察：{text(p.issue.last_observed_at)}；完成 Turn 数：{p.issue.turn_count}", "",
        "## 4. 关键证据", "| ID | 类别 / 状态 | 摘要 | 时间 / 对象 / 任务版本 | 来源 / 时效 |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {text(e.evidence_id)} | {text(e.category)} / {e.status} | {text(e.summary)} | {e.observed_at.isoformat()} / {text(e.target_subject)} / {e.task_version} | {text(e.origin)} / {'历史、可能过时' if e.stale else '生成时有效'} |" for e in p.evidence_summary]
    if not p.evidence_summary: lines.append("无直接检测证据。")
    lines += ["", "## 5. 假设与排除项"]
    lines += [f"- {text(h.name)} [{h.state}]：{text(h.summary)}；证据 {text(', '.join(h.evidence_ids))}" for h in p.excluded_or_weakened_hypotheses] or ["未形成可核验假设。"]
    lines += ["", "## 6. 已尝试 / 跳过 / 失败的修复", "创建时间不等于执行开始；未记录实际开始时间的步骤不补造时间。", "| 步骤 / 计划版本 | 状态 | 用户报告结果 | 风险 | 备注 | 完成 / 失败时间 |", "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {text(s.title)} / v{s.plan_version} | {s.status} | {text(s.outcome)} | {text(s.risk)} | {text(s.user_note)} | {text(s.completed_at)} |" for s in p.remediation_summary]
    lines += ["", "## 7. Before / After 验证", "客观指标与用户主观反馈分列；历史验证不代表当前状态。", "| 验证 ID / 关联步骤 | 状态 / 结果 | 关键差异（客观） | 用户反馈（主观） | 完成时间 / 时效 |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {c.verification_id} / {text(', '.join(map(str,c.related_step)))} | {text(c.status)} / {text(c.result)} | {text('; '.join(c.key_diffs) or '无可比较 After')} | {text(c.user_observation)} | {text(c.completed_at)} / {'历史或可能过时' if c.historical else '生成时记录'} |" for c in p.verification_summary]
    lines += ["", "## 8. 当前处理状态", *[f"- {key}：{text(value)}" for key,value in p.resolution.model_dump().items()], "", "## 9. 交接原因",
        f"- {text(p.escalation_reason.reason_code)} ({p.escalation_reason.triggered_by})：{text(p.escalation_reason.summary)}", "", "## 10. 建议人工核查项",
        *[f"- {text(c)}" for c in p.recommended_handoff_checks], "", "## 11. 完整度与限制", f"- {p.completeness}", *[f"- {text(n)}" for n in p.completeness_notes],
        "", "## 12. 隐私处理", f"- 已移除 / 不采集：{text(', '.join(p.privacy.redacted_fields))}", f"- 私有 IP 掩码：{'开启' if p.privacy.private_ip_masked else '未开启（保留已有私有 IP 便于授权人员排查）'}",
        "- 未包含完整聊天、原始快照、原始 Tool JSON、模型隐藏推理、系统提示词或数据库转储。", "", "## References（参考资料，不是实时证据）", *[f"- {text(r)}" for r in p.source_refs]]
    if p.is_demo: lines.insert(2, "> **DEMO / 模拟数据 — 不可作为真实网络测量或实际报修依据。**")
    return "\n".join(lines) + "\n"


def export_package(package, format="md", *, max_bytes=1_000_000):
    if format not in {"md","json"}: raise ValueError("unsupported format")
    if package_digest(package) != package.package_digest: raise ValueError("invalid package digest")
    package = safe_package(package)
    content = (markdown(package) if format == "md" else package.model_dump_json(indent=2)).encode("utf-8")
    if len(content) > max_bytes: raise DiagnosisReportTooLargeError("报修材料超过导出大小限制。")
    return DiagnosisReportArtifact(content=content,media_type="text/markdown; charset=utf-8" if format == "md" else "application/json",
        filename=f"netpilot-escalation-{package.package_id}-v{package.package_version}.{format}")
