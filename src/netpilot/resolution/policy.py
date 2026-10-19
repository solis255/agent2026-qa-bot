"""Escalation recommendations are structured decisions, never real tickets."""
from netpilot.resolution.models import EscalationDecision


def safe_pending(plan):
    return [s for s in plan.steps if s.status == "pending" and s.risk == "low" and not s.requires_admin] if plan and plan.status in {"proposed","in_progress"} and plan.readiness != "not_ready" else []


class EscalationPolicy:
    def __init__(self, threshold=2):
        if not 1 <= threshold <= 20: raise ValueError("threshold must be 1..20")
        self.threshold = threshold

    def evaluate(self, *, plan, cycles, user_requested=False, hypotheses=(), evidence=(), insufficient_observability=False):
        def decision(code, summary):
            return EscalationDecision(recommended=True, reason_code=code, summary=summary)
        if user_requested:
            return decision("user_requested","用户主动请求人工支持；仅提供建议和诊断报告，未向任何外部系统提交工单。")
        no_safe = not safe_pending(plan)
        if plan and plan.status not in {"superseded","cancelled"} and no_safe:
            if any(s.status == "pending" and s.requires_admin for s in plan.steps):
                return decision("admin_required","后续动作需要管理员权限，超出安全引导范围；不会提权或执行。")
            if any(s.status == "pending" and s.risk in {"medium","high"} for s in plan.steps):
                return decision("no_safe_remediation_left","剩余动作超出低风险范围，停止自动引导并建议人工核验。")
        # Superseded/failed/inconclusive cycles are not completed attempts.
        streak = 0
        for cycle in reversed(cycles):
            if cycle.status != "completed" or cycle.result not in {"improved","unchanged","worsened"}: continue
            if cycle.result == "improved": break
            streak += 1
        if streak >= self.threshold:
            return decision("repeated_no_improvement",f"连续 {streak} 轮有效复核没有改善；" + ("已无剩余安全步骤，建议人工进一步排查。" if no_safe else "仍可选择剩余安全步骤，也可请求人工核验。"))
        if cycles and cycles[-1].status == "completed" and cycles[-1].result == "worsened":
            return decision("verification_worsened","关键指标变差，请暂停继续尝试并考虑人工核验；不代表故障不可修复。")
        # Only an explicitly supported infrastructure hypothesis with multiple
        # independently scoped abnormal observations can recommend escalation.
        abnormal = {r.evidence_id:r for r in evidence if r.status == "abnormal"}
        for hypothesis in hypotheses:
            supporting = [abnormal[eid] for eid in set(hypothesis.supporting_evidence_ids) if eid in abnormal]
            identities = {(r.tool_name, r.tool_signature) for r in supporting}
            if no_safe and hypothesis.name == "infrastructure_issue" and hypothesis.status == "supported" and len(identities) >= 2:
                return decision("infrastructure_suspected","多条结构化依据支持基础设施/服务端问题的可能，且无剩余安全用户侧步骤；需人工核验，不等于已确认学校网络故障。")
        if no_safe and plan and plan.steps and plan.status not in {"superseded","cancelled"}:
            if all(s.status == "skipped" for s in plan.steps):
                return decision("user_declined_remaining_steps","用户未继续执行剩余安全步骤；跳过不表示措施无效。")
            if insufficient_observability:
                return decision("insufficient_observability","当前缺少继续诊断所需的直接可观测性或有效复核，建议人工补充检测；不把采集失败当作修复无效。")
            if all(s.status != "pending" for s in plan.steps):
                return decision("no_safe_remediation_left","当前没有剩余低风险步骤；已完成、跳过和未能完成的动作分别记录，不表示所有措施均无效。")
        return EscalationDecision()
