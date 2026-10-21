"""Local, evidence-backed decision summaries, never model hidden reasoning."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator
from netpilot.privacy import safe_value

from netpilot.agent.coverage import DiagnosticGoal, normalize_observations
from netpilot.agent.intent import TurnIntent
from netpilot.agent.hypotheses import track_hypotheses
from netpilot.llm import ChatMessage, ChatRole


class ReasoningTraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=1)
    phase: Literal["intent", "planning", "evidence", "hypothesis", "decision", "finalization", "state_change", "fallback"]
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1600)
    evidence_ids: list[str] = Field(default_factory=list)
    hypothesis_names: list[str] = Field(default_factory=list)
    decision: str | None = Field(default=None, max_length=80)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: Literal["info", "success", "warning", "error"] = "info"
    turn_index: int = Field(default=1, ge=1)
    task_version: int = Field(default=1, ge=1)
    event_origin: Literal["agent", "client_snapshot", "remediation", "verification", "resolution", "escalation"] = "agent"

    @model_validator(mode="after")
    def privacy_safety(self):
        self.__dict__.update(safe_value(self).__dict__)
        return self


def trace_signature(step: ReasoningTraceStep) -> tuple:
    return (
        step.turn_index, step.task_version, step.phase, step.title,
        tuple(sorted(set(step.evidence_ids))), step.decision,
    )


def trim_reasoning_trace(steps: Sequence[ReasoningTraceStep], limit: int = 50) -> list[ReasoningTraceStep]:
    """Prefer recent decisions/state changes over old evidence/planning detail."""

    if limit < 1:
        raise ValueError("reasoning trace limit must be positive")
    priority = {"planning": 0, "evidence": 1, "intent": 2, "hypothesis": 2,
                "decision": 2, "finalization": 2, "state_change": 3, "fallback": 3}
    ordered = sorted(steps, key=lambda step: step.step_index)
    recent_count = max(1, limit // 2)
    recent = ordered[-recent_count:]
    selected = recent + sorted(ordered[:-recent_count], key=lambda step: (priority[step.phase], step.step_index), reverse=True)[:max(0, limit - len(recent))]
    return sorted(selected, key=lambda step: step.step_index)


def merge_reasoning_trace(existing, current, limit: int = 50) -> list[ReasoningTraceStep]:
    merged = list(existing)
    known = {trace_signature(step) for step in merged}
    last_index = max((step.step_index for step in merged), default=0)
    for step in current:
        signature = trace_signature(step)
        if signature in known:
            continue
        last_index = max(last_index + 1, step.step_index)
        merged.append(step.model_copy(update={"step_index": last_index}))
        known.add(signature)
    return trim_reasoning_trace(merged, limit)


_INTENTS = {
    TurnIntent.DIAGNOSE: "实时网络诊断", TurnIntent.CLARIFY: "补充必要信息",
    TurnIntent.ANALYZE_EXISTING: "分析已有证据", TurnIntent.KNOWLEDGE_REQUEST: "知识库问答",
    TurnIntent.REPORT_REQUEST: "整理运维报告", TurnIntent.COMPARE: "比较已有证据",
    TurnIntent.FOLLOWUP_ACTION: "依据已有证据提供后续建议", TurnIntent.META_FEEDBACK: "处理回答反馈",
    TurnIntent.STATE_CHANGED: "环境变化后的重新诊断", TurnIntent.GENERAL_QUESTION: "一般知识问答",
    TurnIntent.HISTORY_ANALYSIS: "持久化历史分析",
}
_COVERAGE = {"network_config": "网络配置", "dns": "DNS", "ip_connectivity": "IP 连通性",
             "application": "HTTP/TCP", "web_path": "网页访问路径", "tcp": "TCP", "any_network": "必要网络检查"}
_HYPOTHESES = {
    "dns_resolution_path_failure": "DNS 解析链路异常",
    "local_dns_configuration_issue": "本机 DNS 配置问题",
    "proxy_dns_interception": "代理 DNS 接管",
    "single_site_failure": "单一站点故障",
    "overall_ip_connectivity_failure": "整体 IP 网络中断",
}
_STATUS = {"possible": "待验证", "supported": "证据支持", "weakened": "被削弱", "excluded": "已排除"}
_TOOLS = {"get_network_info": "本机网络配置", "dns_lookup": "DNS 解析", "ping_host": "IP 可达性",
          "tcp_check": "TCP 连接", "http_check": "HTTP 访问", "traceroute": "路径可达性"}


class ReasoningTraceBuilder:
    def __init__(self, *, previous=(), turn_index=1, task_version=1, enabled=True, max_steps=50):
        self.enabled = enabled
        self.max_steps = max_steps
        self.turn_index = turn_index
        self.task_version = task_version
        self.steps: list[ReasoningTraceStep] = []
        self.last_index = max((step.step_index for step in previous), default=0)
        self._hypotheses: dict[str, str] = {}
        self.intent: TurnIntent | None = None
        self._evidence_ids: list[str] = []

    def append(self, phase, title, summary, *, evidence_ids=(), hypothesis_names=(), decision=None, severity="info"):
        if not self.enabled:
            return
        step = ReasoningTraceStep(
            step_index=self.last_index + 1, phase=phase, title=title, summary=summary,
            evidence_ids=sorted(set(evidence_ids)), hypothesis_names=sorted(set(hypothesis_names)),
            decision=decision, severity=severity, turn_index=self.turn_index, task_version=self.task_version,
        )
        if any(trace_signature(existing) == trace_signature(step) for existing in self.steps):
            return
        self.last_index += 1
        self.steps = trim_reasoning_trace([*self.steps, step], self.max_steps)

    def begin(self, classification, policy, sufficiency, *, state_changed=False, evidence=(), history_count=0, history_available=True):
        self.intent = classification.intent
        self._evidence_ids = [record.evidence_id for record in evidence]
        self._hypotheses = {item.name: item.status for item in track_hypotheses(evidence=evidence)}
        self.append("intent", "识别任务", f"本轮识别为 {_INTENTS[classification.intent]}（{classification.intent.value}）。")
        if state_changed:
            self.append("state_change", "检测到环境变化",
                        f"旧观察仅保留用于前后对比；新诊断进入 task_version={self.task_version}。", decision="recheck")
        if policy.allow_network_tools and policy.max_new_calls != 0:
            required = " / ".join(_COVERAGE.get(name, name) for name in sufficiency.required_coverage)
            self.append("planning", "制定检测计划", f"按需验证 {required}；只调用白名单只读工具，不因单一异常提前确认根因。", decision="continue")
        elif policy.allow_rag:
            self.append("planning", "查询校园知识库", "仅检索参考资料，区分 official/community/maintainer，不将资料当作实时网络状态。", decision="rag")
        else:
            self.append("planning", "复用现有上下文", "本轮不执行新的网络检测；使用对话与现有结构化证据完成用户目标。")
        if classification.intent is TurnIntent.HISTORY_ANALYSIS:
            self.append("evidence", "读取持久化诊断历史",
                        f"当前账号可用的 Diagnosis History 为 {history_count} 条；" + ("仅基于实际记录比较，不补造记录。" if history_available else "历史存储当前不可用。"))
            self.append("decision", "分析当前用户历史", "禁止重新执行网络检测，按实际持久化记录进行跨 Session 比较。", decision="history_analysis")
        elif not policy.allow_network_tools and not policy.allow_rag:
            decisions = {TurnIntent.CLARIFY: ("优先追问", "信息不足，先询问影响范围和连接情况，不猜测故障。", "clarify"),
                         TurnIntent.META_FEEDBACK: ("处理用户反馈", "不调用网络 Tool；直接回应反馈，不重新诊断 DNS。", "meta_feedback"),
                         TurnIntent.REPORT_REQUEST: ("生成运维报告", "复用已有 Evidence 整理报告，不重新调用网络工具。", "report")}
            decisions[TurnIntent.GENERAL_QUESTION] = ("直接回答一般问题", "不主动运行网络工具；校园服务规定缺少资料时不得补造依据。", "knowledge_no_tools")
            title, summary, decision = decisions.get(classification.intent, ("分析已有证据", "复用已有观察，说明支持项与证据限制，不重新检测。", "reuse"))
            self.append("decision", title, summary, decision=decision)
        if evidence:
            self.append("evidence", "复用已有证据", f"当前任务可复用 {len(evidence)} 条结构化观察；不会重复执行等价工具。",
                        evidence_ids=[record.evidence_id for record in evidence])

    def observe(self, *, steps, evidence, hypotheses):
        if not self.enabled:
            return
        self._evidence_ids = sorted({item.evidence_id for item in normalize_observations(steps=steps, evidence=evidence)})
        groups = defaultdict(list)
        for item in normalize_observations(steps=steps):
            groups[(item.tool_name, item.status)].append(item)
        for (tool, status), items in groups.items():
            ids = [item.evidence_id for item in items]
            if tool == "knowledge_search":
                results = [result for item in items for result in item.data.get("results", []) if isinstance(result, dict)]
                types = sorted({result.get("source_type") for result in results if result.get("source_type") in {"official", "community", "maintainer"}})
                title = "获得知识库参考资料" if results else "知识检索未提供可用资料"
                summary = f"检索到 {len(results)} 个资料片段；来源类型：{' / '.join(types) or '无'}。资料不替代实时 Evidence，不复制完整 chunk。"
            elif tool in _TOOLS:
                label = {"normal": "正常", "abnormal": "异常", "error": "执行失败", "blocked": "被安全策略阻止", "inconclusive": "尚不能判断"}.get(status, "尚不能判断")
                title = f"{_TOOLS[tool]}{label}"
                summary = f"{len(items)} 条{_TOOLS[tool]}观察为{label}；"
                if tool == "dns_lookup" and status == "abnormal":
                    count = len({item.arguments.get("domain") for item in items if item.arguments.get("domain")})
                    summary += f"涉及 {count} 个不同域名，支持解析链路异常，但不能单独定位本机 DNS、校园 DNS 或代理。"
                else:
                    summary += "只解释已检查范围，不据此推断未验证的网络状态。"
            else:
                continue
            # Aggregate a category across batches rather than duplicating a Tool timeline.
            previous = next((step for step in self.steps if step.phase == "evidence" and step.title == title), None)
            if previous is not None:
                self.steps.remove(previous)
                self.steps.append(previous.model_copy(update={"summary": summary, "evidence_ids": sorted(set(ids))}))
                self.steps.sort(key=lambda step: step.step_index)
            else:
                self.append("evidence", title, summary, evidence_ids=ids, severity="warning" if status != "normal" and tool != "knowledge_search" else "info")
        changed = [item for item in hypotheses if self._hypotheses.get(item.name, "possible") != item.status]
        if changed:
            self.append("hypothesis", "候选原因更新",
                        "；".join(f"{_HYPOTHESES.get(item.name, '候选原因')}：{_STATUS[item.status]}（{self._hypotheses.get(item.name, 'possible')} → {item.status}）" for item in changed),
                        evidence_ids=[identifier for item in changed for identifier in [*item.supporting_evidence_ids, *item.contradicting_evidence_ids]],
                        hypothesis_names=[item.name for item in changed])
        self._hypotheses = {item.name: item.status for item in hypotheses}

    def assess(self, sufficiency, hypotheses):
        if sufficiency.goal is DiagnosticGoal.NON_DIAGNOSTIC:
            return
        if sufficiency.sufficient:
            self.append("decision", "证据覆盖已满足目标", "当前 Coverage 已满足用户目标，可停止新增检测；覆盖充分不等于已确定唯一根因。", decision="stop", evidence_ids=self._evidence_ids)
        else:
            missing = " / ".join(_COVERAGE.get(name, name) for name in sufficiency.missing_coverage)
            limits = "；解析异常仍不能区分本机 DNS、校园 DNS 与代理接管" if any(item.name == "dns_resolution_path_failure" for item in hypotheses) else ""
            self.append("decision", "继续补充独立证据", f"Coverage 尚缺：{missing}{limits}。只补充最少必要检测。", decision="continue", evidence_ids=self._evidence_ids)

    def finish(self, result):
        if not self.enabled:
            return []
        if result.reused_evidence_ids:
            self.append("evidence", "使用已留存的观察", f"本轮复用 {len(result.reused_evidence_ids)} 条既有 Evidence。", evidence_ids=result.reused_evidence_ids)
        if result.fallback_reason is not None or result.status.value == "llm_error":
            reason = getattr(result.fallback_reason, "value", None)
            detail = {"max_tool_rounds": "自动检测已达到步骤上限", "invalid_tool_loop": "模型工具请求不符合当前执行策略",
                      "llm_error": "模型调用未能正常完成", "finalization_failed": "最终回答整理未能正常完成",
                      "llm_empty_response": "模型未提供有效回答"}.get(reason, "模型调用未能正常完成")
            self.append("fallback", "进入安全兜底", detail + "；系统如实返回已有依据与限制，不将失败当作检测成功。", decision="fallback", severity="warning")
        if self.intent in {TurnIntent.DIAGNOSE, TurnIntent.STATE_CHANGED}:
            if result.evidence_sufficiency is not None and not result.evidence_sufficiency.sufficient:
                self.append("decision", "以证据限制结束本轮", "受执行上限、失败或尚缺 Coverage 影响，本轮只能给出有限结论；不宣称证据充分。", decision="stop_limited", severity="warning")
            supported = [item for item in result.hypotheses if item.status == "supported"]
            summary = ("当前证据最支持：" + " / ".join(_HYPOTHESES.get(item.name, "候选原因") for item in supported) + "；未经验证的根因仍待确认。") if supported else "仅汇总实际观察与覆盖缺口，不将候选原因写成已确认事实。"
        else:
            summary = {TurnIntent.REPORT_REQUEST: "已按现有对话与 Evidence 生成报告，不新增网络检测。",
                       TurnIntent.META_FEEDBACK: "本轮直接处理用户反馈，不套用新的网络诊断流程。",
                       TurnIntent.HISTORY_ANALYSIS: "基于当前账号实际历史记录完成比较，记录不足或不可用时如实说明。",
                       TurnIntent.KNOWLEDGE_REQUEST: "基于知识资料形成回答或可溯源的片段兜底，资料来源与实时证据保持分离。",
                       TurnIntent.CLARIFY: "先收集必要信息，当前未确认网络故障。"}.get(self.intent, "依据已有上下文完成回答，并保留证据限制。")
            if self.intent is TurnIntent.HISTORY_ANALYSIS and result.history_context_records == 0:
                summary = "没有可用的当前账号历史记录，已明确说明不足；未补造跨 Session 比较。"
            if self.intent is TurnIntent.KNOWLEDGE_REQUEST and not result.sources:
                summary = "当前没有可用的知识来源，必须明确说明依据不足；未把实时网络状态当作资料。"
        self.append("finalization", "形成诊断依据摘要", summary, decision="finalize")
        return list(self.steps)

    def optional_summary(self, llm, result):
        """One optional selection call; only existing verified summaries can be exposed."""
        if not self.enabled or len(self.steps) < 2:
            return result
        selected = self.steps[-12:]
        safe_input = [{"step_index": item.step_index, "phase": item.phase, "summary": item.summary} for item in selected]
        result = result.model_copy(update={"reasoning_summary_llm_used": True})
        try:
            response = llm.chat([
                ChatMessage(role=ChatRole.SYSTEM, content=(
                    "根据结构化诊断状态选择简洁、可验证的诊断依据摘要。只选择关键证据、候选原因变化、继续/停止与结论依据。"
                    "不要输出未被证据支持的推测、隐藏推理、我想、我猜或我考虑。"
                    "只返回选中的 2～5 个 step_index 的 JSON 数组；系统会用原有摘要生成 2～5 个 bullet，不采用自由文本。")),
                ChatMessage(role=ChatRole.USER, content=json.dumps(safe_input, ensure_ascii=False)),
            ], tools=None, tool_choice="none", max_tokens=160, temperature=0)
            result = result.model_copy(update={
                "usage": result.usage.add(response.usage),
                "llm_duration_ms": result.llm_duration_ms + response.duration_ms,
                "reasoning_summary_prompt_tokens": response.usage.prompt_tokens,
                "reasoning_summary_completion_tokens": response.usage.completion_tokens,
            })
            indices = json.loads(response.content or "null")
            known = {item.step_index: item for item in selected}
            if response.tool_calls or response.finish_reason in {"length", "content_filter"} or not isinstance(indices, list):
                return result
            if not 2 <= len(indices) <= 5 or any(type(index) is not int or index not in known for index in indices) or len(set(indices)) != len(indices):
                return result
            self.append("finalization", "诊断依据要点", "\n".join("- " + known[index].summary for index in indices), decision="summary")
        except Exception:
            # Optional enrichment must never change the answer or disclose error payloads.
            pass
        return result
