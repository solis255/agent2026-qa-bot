"""Fixed, approachable questions and canonical answers, never model text parsing."""
import re

from netpilot.environment import OS_LABELS, ACCESS_LABELS, SCOPE_LABELS
from .models import ContextAnswer, ContextChoice, ContextQuestion, CONTEXT_VALUES
from .needs import is_unknown

QUESTIONS = {
    "affected_scope": "是所有联网功能都不能用，还是只有网页或某个服务有问题？",
    "network_access": "你现在连接的是哪种网络？",
    "os_family": "你准备在哪种设备系统上操作？",
    "vpn_enabled": "你现在有没有开启 VPN？不清楚也没关系。",
    "proxy_enabled": "你现在有没有开启代理软件（例如 Clash）？不清楚也没关系。",
}
LABELS = {
    "affected_scope": {**SCOPE_LABELS, "web_only":"只有网页有问题，其他应用能用", "all_network":"其他应用也不能联网", "single_service":"只有某个网站或服务有问题", "internal_resource":"只有校内资源有问题", "unknown":"不清楚"},
    "network_access": {**ACCESS_LABELS, "unknown":"不清楚"},
    "os_family": {**OS_LABELS, "unknown":"不清楚"},
    "vpn_enabled": {"true":"VPN 已开启", "false":"VPN 没开启", "unknown":"不清楚"},
    "proxy_enabled": {"true":"代理已开启", "false":"代理没开启", "unknown":"不清楚"},
}


def plan_context_question(assessment, environment, acquisition_state):
    for name in assessment.missing_fields:
        if name in acquisition_state.asked_fields or not is_unknown(environment, name):
            continue
        return ContextQuestion(field=name, question=QUESTIONS[name], choices=[
            ContextChoice(value=value, label=LABELS[name][value]) for value in CONTEXT_VALUES[name]])
    return None


def answer_values(answer: ContextAnswer):
    value = answer.value
    if answer.field in {"vpn_enabled", "proxy_enabled"}:
        value = None if value == "unknown" else value == "true"
    return {answer.field: value}


def free_text_answer(field, message):
    """Interpret short replies only to the actual pending question."""
    text = re.sub(r"[\s。！!，,]", "", message).casefold()
    if re.fullmatch(r"(?:我)?(?:也)?(?:不清楚|不知道|没注意|不确定|不了解)", text):
        return ContextAnswer(field=field, value="unknown")
    for value, label in LABELS[field].items():
        if text == re.sub(r"\s", "", label).casefold():
            return ContextAnswer(field=field, value=value)
    aliases = {
        "os_family": {"win11":"windows", "win10":"windows", "windows11":"windows", "苹果电脑":"macos", "安卓":"android", "iphone":"ios"},
        "network_access": {"校园无线":"campus_wifi", "校园网线":"campus_wired", "在校外":"off_campus"},
        "affected_scope": {"能正常使用":"web_only", "微信能用":"web_only", "微信正常":"web_only", "也不能联网":"all_network", "都不能联网":"all_network", "只有部分网站":"single_service"},
        "vpn_enabled": {"开着":"true", "开了":"true", "没开":"false", "关了":"false"},
        "proxy_enabled": {"开着":"true", "开了":"true", "没开":"false", "关了":"false"},
    }
    value = aliases.get(field, {}).get(text)
    return ContextAnswer(field=field, value=value) if value else None
