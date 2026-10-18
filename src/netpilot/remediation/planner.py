"""Deterministic, target-scoped selection from approved actions, no LLM calls."""
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit

from netpilot.diagnostic_target import matches_target
from netpilot.remediation.catalog import CATALOG
from netpilot.remediation.models import RemediationPlan, RemediationReadiness, RemediationSource, RemediationStep
from netpilot.remediation.safety import validate_catalog, validate_template

CRITICAL_ENVIRONMENT = ("os_family", "os_version", "network_access", "vpn_enabled", "proxy_enabled", "affected_scope", "affected_service")
ISSUE_CATEGORIES = {"dns_resolution_failure":"dns", "local_network_configuration":"gateway_connectivity",
                    "icmp_unreachable":"gateway_connectivity", "tcp_connectivity_failure":"single_service",
                    "http_connectivity_failure":"web_only", "proxy_fake_ip_mapping":"proxy"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def environment_key(environment):
    return digest({key:getattr(environment, key) for key in CRITICAL_ENVIRONMENT})


def scoped_evidence(evidence, target, task_version=None, *, fresh=False):
    now = datetime.now(timezone.utc)
    scopes = {"mock_target"} if target.subject == "mock_client" else {"client_snapshot"} if target.subject == "user_client" and target.relationship_to_netpilot == "remote" else {"execution_host"}
    return [item for item in evidence if item.tool_name != "knowledge_search" and item.reusable and not item.superseded
            and matches_target(item, target) and item.execution_scope in scopes
            and (item.execution_scope != "client_snapshot" or (item.evidence_origin == "client_snapshot" and item.execution_context == "user_client_snapshot"))
            and (task_version is None or item.task_version == task_version)
            and (not fresh or not (item.stale or item.clock_skew_suspected or (item.expires_at and now > item.expires_at)))]


def infer_issue(evidence, environment):
    """Use the existing diagnosis taxonomy, never parse model answer prose."""
    def abnormal(*names):
        return any(item.tool_name in names and item.status == "abnormal" for item in evidence)
    if abnormal("dns_lookup", "client_snapshot.dns_check"):
        return "dns_resolution_failure"
    if abnormal("get_network_info", "client_snapshot.network_config", "client_snapshot.gateway_reachability"):
        return "local_network_configuration"
    if abnormal("ping_host"):
        return "icmp_unreachable"
    if abnormal("http_check"):
        return "http_connectivity_failure"
    if abnormal("tcp_check", "client_snapshot.tcp_connectivity"):
        return "tcp_connectivity_failure"
    return "insufficient_evidence"


def plan_context_key(environment, target, evidence, snapshot, *, task_version=1, symptom="", primary_issue=None):
    fresh = scoped_evidence(evidence, target, task_version, fresh=True)
    return digest({"environment":environment_key(environment), "target":(target.subject,target.target_version),
                   "task_version":task_version, "issue":primary_issue or infer_issue(fresh,environment),
                   "observations":sorted({(item.tool_name,item.status,digest(item.data)) for item in fresh}),
                   "snapshot":snapshot.snapshot_id if snapshot and snapshot.applicable else None,
                   "snapshot_fresh":bool(snapshot and not snapshot.stale and not snapshot.clock_skew_suspected and datetime.now(timezone.utc) <= snapshot.expires_at),
                   "symptom":symptom})


def known_sources(sources):
    result = []
    for item in sources:
        data = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        try:
            source = RemediationSource.model_validate({key:data[key] for key in RemediationSource.model_fields})
            url = urlsplit(source.source)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                continue
        except (ValueError, KeyError, TypeError):
            continue
        if source.source_ref not in {entry.source_ref for entry in result}:
            result.append(source)
    return sorted(result, key=lambda item:item.source_type == "community")[:8]


class RemediationPlanner:
    def __init__(self, max_steps=5):
        if not 1 <= max_steps <= 10:
            raise ValueError("max_steps must be 1..10")
        self.max_steps = max_steps
        validate_catalog(CATALOG)

    def build_plan(self, environment_profile, diagnostic_target, diagnosis=None, hypotheses=(), evidence=(),
                   client_snapshot_summary=None, knowledge_sources=(), *, plan_version=1, task_version=1,
                   user_message="", previous_plans=()):
        env, target = environment_profile, diagnostic_target
        all_records = scoped_evidence(evidence, target, task_version)
        fresh = scoped_evidence(evidence, target, task_version, fresh=True)
        fresh_ids = {item.evidence_id for item in fresh}
        supported = [item for item in hypotheses if item.status == "supported" and fresh_ids.intersection(item.supporting_evidence_ids)]
        issue = infer_issue(fresh, env)
        # A supplied structured diagnosis is accepted only with current fresh evidence.
        supplied = getattr(diagnosis, "primary_issue", None)
        if fresh and supplied in ISSUE_CATEGORIES and ISSUE_CATEGORIES[supplied] == ISSUE_CATEGORIES.get(issue):
            issue = supplied
        category = ISSUE_CATEGORIES.get(issue, "unknown")
        symptom = "web" if re.search(r"网页|网站|浏览器|http|公网页面", user_message, re.I) else ""
        if env.affected_scope == "web_only": symptom = "web"
        if env.affected_scope == "single_service" and category in {"single_service", "web_only"}:
            category = "single_service"
        auth = env.network_access in {"campus_wifi", "campus_wired"} and bool(
            re.search(r"未认证|认证失效|需要认证|认证页面打不开", user_message) or
            any(item.data.get("status_code") == 511 for item in fresh))
        if auth and category == "unknown": category = "campus_auth"
        if target.subject == "unknown":
            readiness = RemediationReadiness(status="not_ready",reason="诊断对象尚不明确，请先确认要检查的设备。")
        elif category != "unknown" and fresh:
            readiness = RemediationReadiness(status="ready",reason="当前对象存在可操作的结构化异常证据" + ("及有证据关联的支持假设" if supported else "") + "，仅提供批准的低风险手动步骤。")
        elif symptom or env.affected_scope in {"web_only", "single_service"} or auth or (not fresh and any(item.status in {"normal","abnormal"} for item in all_records)):
            readiness = RemediationReadiness(status="limited",reason="只有有限现象、过期/时钟不明快照或不完整证据，只提供通用低风险确认步骤。")
        else:
            readiness = RemediationReadiness(status="not_ready",reason="故障类型和证据不足，先补充影响范围或当前设备证据，不生成伪精确修复计划。")
        if readiness.status == "limited": category = "unknown"
        sources = known_sources(knowledge_sources)
        blocked = {step.equivalence_key for plan in previous_plans
                   if (plan.target_subject,plan.target_version) == (target.subject,target.target_version)
                   for step in plan.steps if step.status != "pending"}
        # Unknown VPN/proxy requires confirmation; true does not imply it should be disabled.
        public = (env.affected_scope == "web_only" or symptom == "web") and env.affected_scope not in {"internal_resource", "single_service"} and not re.search(r"内网|校内资源|校园内部|依赖\s*VPN",user_message,re.I)
        candidates = []
        for template in CATALOG.values():
            validate_template(template)
            if readiness.status == "not_ready" or template.equivalence_key in blocked:
                continue
            categories = {category}
            if category in {"dns", "web_only"} and readiness.status == "ready":
                if env.vpn_enabled is True and public: categories.add("vpn")
                if env.proxy_enabled is True and public: categories.add("proxy")
            if not categories.intersection(template.issue_types): continue
            if target.subject not in template.applicable_targets: continue
            if "any" not in template.applicable_os and env.os_family not in template.applicable_os: continue
            if "any" not in template.applicable_network_access and env.network_access not in template.applicable_network_access: continue
            if template.template_id == "reconnect_network" and env.network_access in {"campus_wifi","campus_wired"}: continue
            if template.template_id == "reopen_browser" and category == "single_service": continue
            if template.template_id == "confirm_vpn_proxy" and env.vpn_enabled is not None and env.proxy_enabled is not None: continue
            if "vpn_true_public" in template.prerequisites and not (env.vpn_enabled is True and public): continue
            if "proxy_true_public" in template.prerequisites and not (env.proxy_enabled is True and public): continue
            if "auth_suspected" in template.prerequisites and not auth: continue
            if "campus_sources" in template.prerequisites and not (sources and env.network_access in {"campus_wifi","campus_wired"}): continue
            if readiness.status == "limited" and template.changes_system_state: continue
            candidates.append(template)
        selected = []; seen = set()
        for template in sorted(candidates,key=lambda item:(item.priority,item.template_id)):
            if template.equivalence_key in seen: continue
            selected.append(template); seen.add(template.equivalence_key)
            if len(selected) == self.max_steps: break
        if not selected and readiness.status != "not_ready":
            readiness=RemediationReadiness(status="not_ready",reason="适用的批准步骤已尝试、跳过或暂无安全模板；不重复无效动作，也不升级风险，请补充新证据。")
        binding = "Mock 模拟终端（仅演示，不代表真实校园网络）" if target.subject == "mock_client" else "NetPilot 服务主机（仅由有权限的维护者手动操作）" if target.subject == "netpilot_host" else "你当前浏览器所在设备（不是 NetPilot 服务主机）"
        steps = []
        for index, template in enumerate(selected,1):
            refs = []; rationale = f"适用对象：{binding}。" + readiness.reason
            if category == "dns": rationale += "已有 DNS 解析异常观察，先处理应用/连接层；不据此认定唯一根因。"
            if template.template_id in {"check_official_guide","campus_reauthenticate"}:
                preferred = [item for item in sources if item.source_type in {"official","maintainer"}]
                refs = [item.source_ref for item in (preferred or sources[:1])]
                if refs and not preferred: rationale += "仅有 community 社区资料，需官方核验，不能作为正式操作依据。"
            steps.append(RemediationStep(
                template_id=template.template_id, equivalence_key=template.equivalence_key, order=index,
                title=template.title, rationale=rationale, instructions=list(template.instructions), risk=template.risk,
                requires_admin=template.requires_admin, changes_system_state=template.changes_system_state,
                reversible=template.reversible, rollback_instructions=list(template.rollback_instructions),
                verification=template.verification, continue_condition="若手动验证已改善，可停止后续操作；这不等于系统已确认故障解决。",
                applicable_os=list(template.applicable_os), applicable_targets=list(template.applicable_targets),
                evidence_ids=[item.evidence_id for item in (fresh if readiness.status == "ready" else [])][:64], source_refs=refs))
        supplied_confidence=getattr(diagnosis,"confidence",None)
        confidence={"high":0.9,"medium":0.6,"low":0.3}.get(supplied_confidence,0.6) if readiness.status == "ready" else 0.2
        return RemediationPlan(plan_version=plan_version, task_version=task_version, target_subject=target.subject,
            target_version=target.target_version, primary_issue=issue, diagnosis_confidence=confidence,
            based_on_evidence_ids=[item.evidence_id for item in all_records][:200],
            based_on_snapshot_id=client_snapshot_summary.snapshot_id if client_snapshot_summary and client_snapshot_summary.applicable else None,
            readiness=readiness.status, readiness_reason=readiness.reason, steps=steps, sources=sources,
            context_key=plan_context_key(env,target,evidence,client_snapshot_summary,task_version=task_version,symptom=symptom,primary_issue=issue),
            environment_key=environment_key(env), symptom=symptom)
