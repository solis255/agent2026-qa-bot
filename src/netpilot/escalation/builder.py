"""Deterministic selection from structured state, without Tools, LLM or I/O."""
from datetime import datetime, timezone
import hashlib
import json
import re

from netpilot.escalation.handoff_catalog import handoff_checks
from netpilot.escalation.models import (
    EscalationPackage, EscalationPrivacyPolicy, PackageTarget, PackageEnvironment,
    PackageIssue, PackageEvidence, PackageHypothesis, PackageRemediation,
    PackageVerification, PackageResolution, PackageReason, PackagePrivacy,
)
from netpilot.escalation.privacy import redact, REDACTED_FIELDS


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _json(value):
    if hasattr(value,"model_dump"): return value.model_dump(mode="json")
    if isinstance(value,dict): return {k:_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_json(v) for v in value]
    return value


def package_digest(package):
    return digest(package.model_dump(mode="json", exclude={"package_digest"}))


def material_request(message):
    """Explicit unquoted request only; not a question about support or a transcript."""
    text = message.strip().rstrip("。！!？?")
    return bool(re.fullmatch(r"(?:请|我要|我需要|帮我|请帮我)?(?:报修|(?:生成|整理|准备)(?:一份)?(?:升级)?报修材料(?:包)?|整理给运维人员)", text))


def _scope(item, target):
    if (item.target_subject, item.target_version) != (target.subject, target.target_version): return False
    if item.evidence_origin == "client_snapshot":
        return target.subject == "user_client" and item.execution_scope == "client_snapshot" and item.execution_context == "user_client_snapshot"
    if item.evidence_origin == "tool":
        if target.subject == "mock_client": return item.execution_scope == "mock_target" and item.execution_context == "mock_provider"
        return (target.subject == "netpilot_host" or target.relationship_to_netpilot == "same_host") and item.execution_scope == "execution_host" and item.execution_context == "netpilot_host"
    return False


def _stale(item, task, now):
    from datetime import timedelta
    expiry = item.expires_at or item.observed_at + timedelta(minutes=15)
    return (item.stale or item.clock_skew_suspected or item.superseded or now > expiry
            or item.observed_at > now + timedelta(minutes=5) or item.task_version != task.task_version)


def _safe_text(task, policy):
    # Also remove known sensitive values wherever repeated in a free-text summary.
    values = set()
    def collect(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if re.search(r"(?i)hostname|computername|ssid|bssid|mac(?:_address)?$|password|passwd|cookie|authorization|api.?key|token|secret|credential|user.?agent|location|latitude|longitude", str(k)):
                    if isinstance(v, (str, int, float)) and len(str(v)) >= 3: values.add(str(v))
                else: collect(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj: collect(v)
    for e in task.evidence:
        collect(e.data); collect(e.arguments)
    def safe(value):
        if value is None: return None
        for secret in sorted(values, key=len, reverse=True): value = value.replace(secret, "[redacted]")
        return redact(value, policy)
    return safe


def _content(task, max_evidence, policy, now):
    target = task.diagnostic_target
    safe = _safe_text(task, policy)
    candidates = [e for e in task.evidence if _scope(e, target)]
    latest = next((c for c in reversed(task.verification_cycles) if (c.target_subject,c.target_version) == (target.subject,target.target_version)), None)
    after_ids = set(latest.after.evidence_ids) if latest and latest.after else set()
    # Fresh first; among these prioritize latest After and abnormal observations.
    candidates.sort(key=lambda e: (_stale(e,task,now), e.evidence_id not in after_ids,
                                    e.status != "abnormal", -e.observed_at.timestamp()))
    selected, keys, aliases = [], {}, {}
    for e in candidates:
        endpoint = e.arguments.get("domain", e.arguments.get("url", e.arguments.get("host", e.data.get("target", ""))))
        key = (e.tool_name, safe(str(endpoint)), e.arguments.get("port"), e.status, _stale(e,task,now))
        if key in keys:
            aliases[e.evidence_id] = keys[key]
            continue
        if len(selected) >= max_evidence: continue
        keys[key] = e.evidence_id
        aliases[e.evidence_id] = e.evidence_id
        stale = _stale(e,task,now)
        origin = {"client_snapshot":"用户主动上传的客户端快照（采集时点，非远程执行）", "tool":"Mock 模拟检测" if target.subject == "mock_client" else "NetPilot 服务主机只读检测"}[e.evidence_origin]
        selected.append(PackageEvidence(evidence_id=safe(e.evidence_id),category=safe(e.tool_name),
            status=e.status if e.status in {"normal","abnormal"} else "unknown",
            summary=("历史 / 可能过时：" if stale else "") + safe(e.summary),observed_at=e.observed_at,
            target_subject=e.target_subject,task_version=e.task_version,origin=origin,stale=stale))
    retained = {e.evidence_id for e in selected}
    fresh_ids={e.evidence_id for e in selected if not e.stale}
    hypotheses = tuple(PackageHypothesis(name=safe(h.name),state=h.status,
        summary=("历史 / 不完整依据，当前需重验：" if not any(safe(aliases.get(eid,"")) in fresh_ids for eid in [*h.supporting_evidence_ids,*h.contradicting_evidence_ids]) else "") + {"supported":"证据支持，尚非唯一根因", "weakened":"反向证据削弱该假设", "excluded":"在已检查范围内排除"}[h.status],
        evidence_ids=tuple(dict.fromkeys(safe(aliases[eid]) for eid in [*h.supporting_evidence_ids,*h.contradicting_evidence_ids] if eid in aliases and safe(aliases[eid]) in retained)))
        for h in task.hypotheses if h.status in {"supported","weakened","excluded"})
    plans = {str(p.plan_id):p for p in [*task.remediation_plan_history,task.remediation_plan] if p and (p.target_subject,p.target_version) == (target.subject,target.target_version)}
    steps = tuple(PackageRemediation(step_id=s.step_id,plan_version=p.plan_version,title=safe(s.title),status=s.status,
        outcome=s.outcome,risk=s.risk,user_note=safe(s.user_note),
        # Creation is not execution start. The current step schema has no started_at.
        started_at=None,completed_at=s.updated_at if s.status in {"completed","failed"} else None)
        for p in plans.values() for s in p.steps if s.status != "pending")
    evidence_by_id = {e.evidence_id:e for e in candidates}
    cycles = []
    for c in task.verification_cycles[-10:]:
        if (c.target_subject,c.target_version) != (target.subject,target.target_version): continue
        historical = c.status == "superseded" or (c.after_task_version is not None and c.after_task_version != task.task_version)
        if c.after:
            historical |= any(eid not in evidence_by_id or _stale(evidence_by_id[eid],task,now) for eid in c.after.evidence_ids)
        cycles.append(PackageVerification(verification_id=c.verification_id,related_step=tuple(c.remediation_step_ids),status=c.status,
            result=c.result,key_diffs=tuple(safe(f"{d.metric} {d.target or ''}: {d.before or '未知'} → {d.after or '未采集'} ({d.change}); {d.interpretation}") for d in c.diffs[:12]),
            user_observation=safe(f"用户主观反馈（非客观检测）：{c.user_observation.symptom_status}；{c.user_observation.note or ''}") if c.user_observation else None,
            completed_at=c.completed_at,historical=historical))
    resolution = task.resolution
    reason = PackageReason(reason_code=resolution.escalation_reason or resolution.reason_code or "escalated",
        summary=safe(resolution.escalation_summary or resolution.reason_summary or "建议人工进一步核验"),triggered_by="resolution") if resolution.state == "escalated" else PackageReason(
        reason_code="user_requested_material",summary="用户主动请求整理报修材料；保持原处理状态，未提交外部工单。",triggered_by="user_request")
    notes = []
    fresh = [e for e in selected if not e.stale and e.status in {"normal","abnormal"}]
    if not fresh: notes.append("缺少当前对象的直接、有效网络证据；不能从用户描述推定实时根因。")
    if len(candidates) > len(selected): notes.append("重复或超出数量上限的证据已合并 / 省略；并非完整原始检测记录。")
    if target.subject == "unknown": notes.append("诊断对象尚未明确。")
    env = task.environment_profile
    if env.os_family == "unknown" or env.network_access == "unknown": notes.append("操作系统或网络接入环境未完整确认。")
    if env.proxy_enabled is None: notes.append("未知代理状态。")
    if not any(e.category == "campus_auth" and not e.stale for e in selected): notes.append("未核验校园认证。")
    if not steps: notes.append("无已执行、跳过或失败的手动修复记录；不能声称已尝试修复。")
    valid_after = bool(cycles and cycles[-1].completed_at and not cycles[-1].historical and cycles[-1].status == "completed")
    if not valid_after: notes.append("缺少可比较的修复后 After 证据" + (" / 客户端新快照。" if target.relationship_to_netpilot == "remote" else "。"))
    issue_in_scope=task.issue_target_version in {None,target.target_version} and task.resolution.reason_code != "target_changed"
    symptom = (task.remediation_symptom or task.current_issue) if issue_in_scope else ""
    if not symptom: notes.append("缺少当前对象的明确问题描述。")
    symptom=symptom or "用户尚未提供当前对象明确症状"
    refs = {}
    for p in plans.values():
        for s in p.sources: refs[s.source_ref] = (s.source_type,s.title,s.source)
    for e in task.evidence:
        if e.tool_name == "knowledge_search":
            for s in e.data.get("results", [])[:20]:
                if isinstance(s,dict) and s.get("source_type") in {"official","maintainer","community"}:
                    from netpilot.rag.schemas import source_ref_for
                    source = str(s.get("source", ""))
                    refs[source_ref_for(source,str(s.get("chunk_id", "")))] = (s["source_type"],str(s.get("title","")),source)
    sources = tuple(safe(f"[{ref}] [{typ}] {title} | {url}" + (" | 社区资料，需官方核验" if typ == "community" else ""))
                    for ref,(typ,title,url) in sorted(refs.items(),key=lambda x: {"official":0,"maintainer":1,"community":2}[x[1][0]])[:8])
    completeness = "limited" if not fresh else "complete" if (target.subject != "unknown" and env.os_family != "unknown" and env.network_access != "unknown" and issue_in_scope and task.remediation_symptom and steps and valid_after) else "partial"
    primary = task.remediation_plan.primary_issue if task.remediation_plan and task.remediation_plan.status != "superseded" and (task.remediation_plan.target_subject,task.remediation_plan.target_version,task.remediation_plan.task_version) == (target.subject,target.target_version,task.task_version) else None
    return dict(target=PackageTarget(subject=target.subject,relationship_to_netpilot=target.relationship_to_netpilot,
        execution_context=target.execution_context,target_version=target.target_version,
        notice="Mock 模拟终端：不代表真实校园网络" if target.subject == "mock_client" else "Local 仅检测运行 NetPilot 的主机；远程客户端证据来自用户上传快照。"),
        environment=PackageEnvironment(**{k:getattr(env,k) for k in PackageEnvironment.model_fields if k != "affected_service"},affected_service=safe(env.affected_service)),
        issue=PackageIssue(title="TJU NetPilot 升级报修材料",original_symptom=safe((task.original_symptom if issue_in_scope else "") or symptom),current_symptom=safe(symptom),primary_issue=safe(primary or "undetermined"),
            started_at=task.issue_started_at if issue_in_scope else None,last_observed_at=max((e.observed_at for e in selected),default=None),turn_count=task.turn_index),
        evidence_summary=tuple(selected),excluded_or_weakened_hypotheses=hypotheses,remediation_summary=steps,verification_summary=tuple(cycles),
        resolution=PackageResolution(**{k:safe(getattr(resolution,k)) if isinstance(getattr(resolution,k),str) else getattr(resolution,k) for k in PackageResolution.model_fields}),
        escalation_reason=reason,recommended_handoff_checks=handoff_checks([e.category for e in selected],mock=target.subject == "mock_client"),source_refs=sources,
        privacy=PackagePrivacy(redacted_fields=REDACTED_FIELDS,private_ip_masked=policy.mask_private_ip),completeness=completeness,completeness_notes=tuple(notes))


def state_fingerprint(task, *, max_evidence=12, policy=None, now=None):
    policy = policy or EscalationPrivacyPolicy()
    content = _content(task,max_evidence,policy,now or datetime.now(timezone.utc))
    # Material/report requests are not new diagnostic observations.
    content["issue"] = content["issue"].model_copy(update={"turn_count":0})
    return digest({"content":_json(content),
        "state_version":task.resolution.state_version,"task_version":task.task_version,"target_version":task.diagnostic_target.target_version,
        "plan_version":task.remediation_plan_version,"latest_verification_id":str(task.verification_cycles[-1].verification_id) if task.verification_cycles else None,
        "policy":policy.model_dump()})


def build_package(task, *, version=1, max_evidence=12, policy=None, now=None):
    if not 1 <= max_evidence <= 50: raise ValueError("invalid evidence limit")
    now = now or datetime.now(timezone.utc)
    policy = policy or EscalationPrivacyPolicy()
    package = EscalationPackage(session_id=task.session_id,package_version=version,generated_at=now,
        created_from_state_version=task.resolution.state_version,created_from_task_version=task.task_version,created_from_target_version=task.diagnostic_target.target_version,
        source_state_fingerprint=state_fingerprint(task,max_evidence=max_evidence,policy=policy,now=now),**_content(task,max_evidence,policy,now))
    return package.model_copy(update={"package_digest":package_digest(package)})
