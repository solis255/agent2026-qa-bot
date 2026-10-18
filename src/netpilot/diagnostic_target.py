"""Diagnostic subject identity, distinct from the actual execution location."""

from datetime import datetime, timezone
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from netpilot.environment import EnvironmentProfile

TargetSubject = Literal["user_client", "netpilot_host", "mock_client", "unknown"]
ExecutionContext = Literal["netpilot_host", "mock_provider", "unavailable"]
ExecutionScope = Literal["execution_host", "target_neutral", "mock_target"]
ProviderKind = Literal["local", "mock", "unavailable"]
TargetSource = Literal["user", "environment", "system", "mock", "inferred"]
TARGET_PRECEDENCE = {"inferred": 0, "system": 1, "environment": 2, "mock": 3, "user": 4}
SUBJECT_LABELS = {"user_client":"当前浏览器设备", "netpilot_host":"NetPilot 服务主机", "mock_client":"Mock 模拟终端", "unknown":"未记录 / 未明确"}
EXECUTION_LABELS = {"netpilot_host":"NetPilot 服务主机", "mock_provider":"Mock Provider", "unavailable":"不可用 / 未记录"}
RELATIONSHIP_LABELS = {"same_host":"同一主机", "remote":"远程", "simulated":"模拟", "unknown":"未知"}


class DiagnosticTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: TargetSubject = "unknown"
    relationship_to_netpilot: Literal["same_host", "remote", "simulated", "unknown"] = "unknown"
    execution_context: ExecutionContext = "unavailable"
    source: TargetSource = "system"
    confidence: Literal["high", "medium", "low"] = "low"
    target_version: int = Field(default=1, ge=1, strict=True)
    limitation_code: Literal["none", "remote_client_not_directly_observable", "unknown_target", "provider_target_mismatch"] = "unknown_target"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TargetBinding(BaseModel):
    """Unknown defaults read legacy data without inventing an observation site."""
    target_subject: TargetSubject = "unknown"
    target_version: int = Field(default=1, ge=1, strict=True)
    execution_context: ExecutionContext = "unavailable"
    execution_scope: ExecutionScope = "execution_host"


def legacy_target() -> DiagnosticTarget:
    return DiagnosticTarget(updated_at=datetime(1970, 1, 1, tzinfo=timezone.utc))


def execution_context_for(provider_kind: str) -> ExecutionContext:
    return {"local":"netpilot_host", "mock":"mock_provider"}.get(provider_kind, "unavailable")


def target_limitation(subject, relationship, provider_kind):
    if subject == "unknown":
        return "unknown_target"
    if provider_kind == "mock":
        return "none" if subject == "mock_client" and relationship == "simulated" else "provider_target_mismatch"
    if provider_kind != "local" or subject == "mock_client":
        return "provider_target_mismatch"
    if subject == "netpilot_host" or (subject == "user_client" and relationship == "same_host"):
        return "none"
    return "remote_client_not_directly_observable" if relationship == "remote" else "unknown_target"


def derive_diagnostic_target(environment: EnvironmentProfile, provider_kind: str, *, same_host_confirmed=False) -> DiagnosticTarget:
    """The boolean is a trusted embedding capability, never a browser/LLM field."""
    mode = environment.client_mode
    values = {"execution_context":execution_context_for(provider_kind)}
    if provider_kind == "mock" or mode == "mock":
        values.update(subject="mock_client", relationship_to_netpilot="simulated", source="mock", confidence="high")
    elif mode == "remote_browser":
        values.update(subject="user_client", relationship_to_netpilot="remote", source="environment", confidence="high")
    elif mode == "server_local":
        values.update(subject="user_client", relationship_to_netpilot="same_host" if same_host_confirmed else "unknown", source="environment", confidence="high" if same_host_confirmed else "low")
    target = DiagnosticTarget(**values)
    return target.model_copy(update={"limitation_code":target_limitation(target.subject, target.relationship_to_netpilot, provider_kind)})


def merge_diagnostic_target(current: DiagnosticTarget, candidate: DiagnosticTarget, provider_kind: str) -> DiagnosticTarget:
    selected = candidate if TARGET_PRECEDENCE[candidate.source] >= TARGET_PRECEDENCE[current.source] else current
    data = selected.model_dump()
    changed_identity = (selected.subject, selected.relationship_to_netpilot) != (current.subject, current.relationship_to_netpilot)
    data.update(target_version=current.target_version + int(changed_identity), execution_context=execution_context_for(provider_kind))
    data["limitation_code"] = target_limitation(selected.subject, selected.relationship_to_netpilot, provider_kind)
    data["updated_at"] = current.updated_at
    if data != current.model_dump():
        data["updated_at"] = datetime.now(timezone.utc)
    return DiagnosticTarget.model_validate(data)


def user_target(subject: Literal["user_client", "netpilot_host"], environment: EnvironmentProfile, provider_kind: str) -> DiagnosticTarget:
    # A browser selection cannot assert co-location, even via a localhost URL.
    relationship = "same_host" if subject == "netpilot_host" else "remote" if environment.client_mode == "remote_browser" else "unknown"
    return DiagnosticTarget(subject=subject, relationship_to_netpilot=relationship,
                            execution_context=execution_context_for(provider_kind), source="user", confidence="high",
                            limitation_code=target_limitation(subject, relationship, provider_kind))


def extract_target_subject(message: str):
    """Only an explicit diagnostic subject, not quoted/hypothetical instructions."""
    if re.search(r'如果|假如|假设|比如|例如|他说|同学|有人|["“”‘’]', message):
        return None
    for clause in re.split(r"[，。；,;\n]", message[:4000].casefold()):
        if re.search(r"不要|无需|不必|别|不是|不想|不检查|不诊断", clause):
            continue
        if re.search(r"检查|检测|诊断|排查|切换|我要|访问|能不能", clause) and re.search(r"(?:netpilot\s*(?:服务主机|服务器|主机)|运行\s*netpilot\s*的.{0,5}(?:服务器|主机))", clause):
            return "netpilot_host"
        if re.search(r"(?:我的|我这台|当前浏览器所在|当前浏览器)(?:\s*)(?:电脑|设备|客户端|手机)|(?:切换|诊断对象).{0,8}当前浏览器设备", clause):
            return "user_client"
    return None


def binding_for(target: DiagnosticTarget, scope: ExecutionScope) -> dict:
    if scope == "target_neutral":
        return {"target_subject":"unknown", "target_version":1, "execution_context":"unavailable", "execution_scope":scope}
    return {"target_subject":target.subject, "target_version":target.target_version, "execution_context":target.execution_context, "execution_scope":scope}


def matches_target(item, target: DiagnosticTarget) -> bool:
    return item.execution_scope == "target_neutral" or (
        target.subject != "unknown" and item.target_subject == target.subject and item.target_version == target.target_version
    )


def target_context(target: DiagnosticTarget) -> str:
    direct = target.limitation_code == "none" and target.execution_context != "unavailable"
    return ("DIAGNOSTIC TARGET\n"
            f"- Subject: {target.subject}\n- Target version: {target.target_version}\n"
            f"- Relationship to NetPilot: {target.relationship_to_netpilot}\n"
            f"- Network tools execute on: {target.execution_context}\n"
            f"- Direct system-level observation of subject: {'available (simulated)' if direct and target.subject == 'mock_client' else 'available' if direct else 'unavailable'}\n"
            f"- Limitation: {target.limitation_code}\n"
            "Local Provider results must not be presented as remote user-client evidence. "
            "Only use current subject/version Network Evidence; Knowledge Sources are target-neutral references. "
            "Use NetPilot 服务主机 for host findings and Mock 模拟终端 for simulated findings.")


def scoped_answer(answer: str, target: DiagnosticTarget) -> str:
    """A visible subject label and conservative wording for actual network answers."""
    if target.subject not in {"netpilot_host", "mock_client"}:
        return answer
    label = SUBJECT_LABELS[target.subject]
    answer = re.sub(r"(?:你的|您的|您这台|你这台)(?:电脑|设备|客户端|主机|网络|本机)", label, answer)
    answer = re.sub(r"(?:你的|您的)(?=\s*(?:DNS|默认网关|网关|路由|IP|网卡|连接))", label + "的", answer, flags=re.I)
    note = "（模拟结果，不代表真实校园网络）" if target.subject == "mock_client" else ""
    return f"诊断对象：{label}{note}\n\n" + answer
