"""Single audit point: increment only when the state actually changes."""
from netpilot.remediation.models import utcnow
from netpilot.resolution.models import ResolutionTransition

# Within an open case evidence/actions may move among the six open states.
# A resolved case must explicitly reopen as diagnosing before any further state.
OPEN_STATES = {"diagnosing","action_required","verifying","improved","unresolved","escalated"}


def transition(current, candidate, *, allow_reopen=False):
    if current.state == "resolved" and candidate.state != "resolved":
        if candidate.state != "diagnosing" or not allow_reopen: raise ValueError("resolved_requires_explicit_reopen")
    if candidate.state != current.state:
        now=utcnow()
        candidate = candidate.model_copy(update={"state_version":current.state_version+1,"updated_at":now,
            "resolved_at":now if candidate.state == "resolved" else None,"escalated_at":now if candidate.state == "escalated" else None})
        audit=ResolutionTransition(from_state=current.state,to_state=candidate.state,state_version=candidate.state_version,
            reason_code=candidate.reason_code or "state_changed",summary=candidate.reason_summary or "诊断状态发生变化。",
            verification_id=candidate.based_on_verification_id,remediation_plan_id=candidate.based_on_remediation_plan_id,
            target_subject=candidate.target_subject,target_version=candidate.target_version,task_version=candidate.task_version,created_at=now)
        return candidate,audit
    if candidate.model_dump(exclude={"updated_at"}) != current.model_dump(exclude={"updated_at"}):
        candidate.updated_at=utcnow()
    return candidate,None
