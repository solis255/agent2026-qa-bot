"""Conservative context requirements: one symptom is not a full questionnaire."""
import re

from netpilot.environment import EnvironmentProfile
from .models import ContextAcquisitionState, EnvironmentNeedAssessment


def is_unknown(environment, name):
    return getattr(environment, name) in (None, "unknown")


def context_topic(intent, message):
    kind = getattr(intent, "value", intent)
    text = message.casefold()
    if kind == "knowledge_request":
        return "platform_setup" if re.search(r"安装|配置步骤|配置客户端", text) else None
    if kind not in {"diagnose", "clarify", "general_question", "compare"}:
        return None
    # Explicit tool/target checks have their own policies. Do not demand a
    # student's environment before a scoped DNS/host/port observation.
    if re.search(r"dns_lookup|tcp_check|ping_host|http_check|traceroute|get_network_info|服务主机|服务器|检查\s*dns|检测\s*dns|诊断\s*dns", text):
        return None
    if not re.search(r"打不开|连不上|无法连接|没网|上不了网|不能上网|网络(?:有问题|不行)|断网|一直失败|连接失败", text):
        return None
    if re.search(r"代理|proxy|clash", text): return "proxy"
    if "vpn" in text: return "vpn"
    if re.search(r"校园网|校园\s*(?:wifi|无线|网线|有线)|校内资源", text): return "campus"
    return "web" if re.search(r"网页|浏览器", text) else "connectivity"


def assess_environment_need(intent, message, environment: EnvironmentProfile,
                            acquisition_state: ContextAcquisitionState, *, has_evidence=False,
                            host_target=False) -> EnvironmentNeedAssessment:
    topic = context_topic(intent, message)
    fields = []
    reason = "request_does_not_require_runtime_environment"
    if topic == "platform_setup":
        fields, reason = ["os_family"], "platform_specific_setup"
    elif topic and not has_evidence and not host_target:
        reason = "symptom_requires_minimal_context"
        fields = ["affected_scope"]
        if topic == "campus": fields.append("network_access")
        if topic == "vpn": fields.append("vpn_enabled")
        if topic == "proxy": fields.append("proxy_enabled")
    missing = [name for name in fields if is_unknown(environment, name)
               and name not in acquisition_state.unknown_fields
               and not (name in environment.field_sources and environment.field_sources[name].source == "user")]
    return EnvironmentNeedAssessment(required=bool(fields), required_fields=fields, missing_fields=missing, reason=reason)
