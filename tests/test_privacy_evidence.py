from uuid import uuid4
from netpilot.agent.task_state import EvidenceRecord
from netpilot.agent.reasoning_trace import ReasoningTraceStep
from netpilot.privacy import safe_value


def test_evidence_and_trace_are_safe_at_creation_and_copy_pass():
    evidence = EvidenceRecord(tool_name="dns_lookup", tool_signature="dns:example.com", status="normal",
        summary="token=evidence-secret", data={"Authorization": "Bearer header-secret", "dns_server": "172.23.0.1"}, turn_index=1)
    assert "evidence-secret" not in evidence.model_dump_json() and "header-secret" not in evidence.model_dump_json()
    assert evidence.data["dns_server"] == "172.23.0.1"
    assert evidence.privacy_metadata.sensitive_values_removed
    assert safe_value(evidence) == evidence
    trace = ReasoningTraceStep(step_index=1, phase="evidence", title="观察", summary="password=trace-secret")
    assert "trace-secret" not in trace.model_dump_json()


def test_session_notes_committed_safe_without_history():
    from escalation_helpers import case
    from netpilot.verification.models import UserVerificationObservation
    task = case()
    # A safe boundary must also cover post-validation model_copy mutations.
    task.remediation_plan.steps[0].user_note = "我的 token=note-secret，重新连接以后还是不行"
    task.resolution.reason_summary = "credential=resolution-secret"
    task.verification_cycles[-1].user_observation = UserVerificationObservation(symptom_status="unchanged_by_user_report", note="password=verification-secret")
    safe = safe_value(task)
    text = safe.model_dump_json()
    assert all(secret not in text for secret in ["note-secret", "resolution-secret", "verification-secret"])
