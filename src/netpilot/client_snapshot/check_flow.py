"""13C orchestration consumes 13B decisions and the existing 12E lifecycle."""
import re
from uuid import uuid4, uuid5

from .check_models import ClientCheckAction, ClientCheckReceipt
from .service import usable_client_snapshot_evidence


def declined(task):
    value = task.client_check.declined
    return bool(value and (value.task_version, value.target_version) ==
                (task.task_version, task.diagnostic_target.target_version))


def reopen_requested(message):
    return bool(re.fullmatch(r"(?:我)?(?:现在可以检查|现在开始网络检查|开始网络检查|我要网络检查)[。！!？?]?", message.strip()))


def client_check_action(task, readiness=None):
    if task is None or task.is_demo or declined(task):
        return None
    target = task.diagnostic_target
    if (target.subject, target.relationship_to_netpilot, task.environment_profile.os_family) != ("user_client", "remote", "windows"):
        return None
    cycle = task.verification_cycles[-1] if task.verification_cycles else None
    recheck = bool(cycle and cycle.status == "awaiting_after_evidence" and
        (cycle.target_subject, cycle.target_version, cycle.after_task_version) ==
        (target.subject, target.target_version, task.task_version))
    readiness = readiness or task.last_diagnostic_readiness
    initial = bool(readiness and (readiness.task_version, readiness.target_version) == (task.task_version, target.target_version)
        and readiness.state == "need_client_evidence" and readiness.recommended_action == "request_client_evidence"
        and readiness.client_evidence_supported is True)
    if not (recheck or initial):
        return None
    mode = "recheck" if recheck else "initial"
    return ClientCheckAction(session_id=task.session_id, task_version=task.task_version,
        target_version=target.target_version, action_id=uuid5(task.session_id, f"client_check:{task.task_version}:{target.target_version}:{mode}"),
        mode=mode, reason="verification_awaiting_after_evidence" if recheck else readiness.reason)


def issue_continuation(task):
    """Called under the Session import lock, only after formal normalization."""
    records = usable_client_snapshot_evidence(task)
    cycle = task.verification_cycles[-1] if task.verification_cycles else None
    if cycle and cycle.status == "awaiting_after_evidence" and records and records[0].observed_at <= cycle.baseline.captured_at:
        task.client_check.pending_continuation = None
        return
    if not records or task.is_demo:
        task.client_check.pending_continuation = None
        return
    task.client_check.pending_continuation = ClientCheckReceipt(receipt_id=uuid4(), snapshot_id=task.client_snapshot_id,
        task_version=task.task_version, target_version=task.diagnostic_target.target_version)


def refresh_readiness_after_upload(task, *, provider_kind):
    """Every result, including stale data, goes through the existing 13B gate."""
    message = task.remediation_symptom or task.original_symptom
    if not message:
        return
    from netpilot.agent.intent import IntentClassification, TurnIntent
    from netpilot.conversation_context.readiness import assess_diagnostic_readiness
    task.last_diagnostic_readiness = assess_diagnostic_readiness(
        classification=IntentClassification(intent=TurnIntent.DIAGNOSE, confidence=1,
            needs_tools=False, needs_rag=False, force_recheck=False, reason="client_evidence_imported"),
        message=message, environment=task.environment_profile, context_question=None,
        target=task.diagnostic_target, provider_kind=provider_kind, reusable_evidence=task.reusable_evidence(),
        task_version=task.task_version, acquisition_state=task.context_acquisition)


def validate_continuation(task, receipt_id):
    receipt = task.client_check.pending_continuation
    if (not receipt or receipt.receipt_id != receipt_id or
        (receipt.task_version, receipt.target_version, str(receipt.snapshot_id)) !=
        (task.task_version, task.diagnostic_target.target_version, task.client_snapshot_id) or
        not usable_client_snapshot_evidence(task)):
        raise ValueError("client_evidence_continuation_not_current")


def check_answer(*, refused=False):
    if refused:
        return "可以暂时不做网络检查。我会先根据现象提供低风险建议，结论保持为信息不足：确认接入与认证状态、比较其他应用和网站，再核对 VPN 或代理开关。需要时可以说“现在可以检查”。"
    return ("目前的信息还不足以判断问题是在 DNS、默认网关还是电脑本身的网络配置。\n\n"
        "可以做一次只读网络检查：不会修改网络设置，不需要管理员权限，不读取密码、Cookie 或浏览记录。"
        "检查在你的 Windows 电脑本地运行，由你主动选择结果文件上传；服务主机检测不能代替你的电脑。")
