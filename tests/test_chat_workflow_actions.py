"""14B contracts through the existing authenticated workflow endpoints."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from client_snapshot_helpers import payload, upload
from conftest import register_test_user
from netpilot.agent import AgentOrchestrator
from netpilot.chat_actions.factory import build_next_chat_action, legacy_chat_action
from netpilot.chat_actions.models import (
    RESOLUTION_CHOICES, ChatAction, RemediationStepAction, ResolutionConfirmationAction, VerificationAction,
)
from netpilot.client_snapshot.check_models import ClientCheckScope
from netpilot.config import Settings
from netpilot.history import DiagnosisStorageError
from netpilot.main import create_app
from netpilot.tools.schemas import DNSLookupData, ToolResult
from resolution_helpers import finished
from target_helpers import TargetLLM, local_app, registry_and_counts
from test_context_acquisition import complete_sse
from test_remediation_api import setup_plan
from verification_helpers import host_cycle, remote_cycle, waiting_cycle


ADAPTER = TypeAdapter(ChatAction)
SCOPE = ("session_id", "action_id", "task_version", "target_subject", "target_version")
PLAN = ("plan_id", "plan_version")
CONFIRMATION = ("verification_id", "resolution_state_version")
CONFLICT = "这一步已经更新，请根据当前对话中的最新提示继续。"


def parsed(action):
    assert ADAPTER.validate_json(ADAPTER.dump_json(action)) == action
    assert legacy_chat_action(action) is None
    return action.model_dump(mode="json")


def success(response):
    assert response.status_code == 200, response.text
    return response.json()


def public_action(client, sid):
    return success(client.get(f"/api/session/{sid}"))["next_chat_action"]


def select(action, fields):
    return {key: action[key] for key in (*SCOPE, *fields)}


def step_feedback(client, action, choice="complete", **overrides):
    return client.patch(
        f"/api/session/remediation-plan/steps/{action['step_id']}",
        json={**select(action, PLAN), "action": choice, **overrides},
    )


def start_verification(client, action, **overrides):
    return client.post(f"/api/session/verification/{action['verification_id']}/start",
                       json={**select(action, PLAN), **overrides})


def confirm(client, action, status="resolved", **overrides):
    return client.post("/api/session/resolution/confirm",
                       json={**select(action, CONFIRMATION), "status": status, **overrides})


def assert_stale(response):
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == CONFLICT


@pytest.fixture
def remote(tmp_path):
    app, counts = local_app(tmp_path)
    with TestClient(app) as client:
        owner, sid, _ = setup_plan(client)
        yield app, client, owner, sid, counts


@pytest.fixture(params=["netpilot_host", "mock_client"])
def diagnostic_workflow(tmp_path, request):
    subject = request.param
    if subject == "netpilot_host":
        app, counts = local_app(tmp_path)
    else:
        app = create_app(Settings(_env_file=None, tju_api_key="test-only", tool_mode="mock",
                                  rag_enabled=False, diagnosis_history_enabled=True,
                                  diagnosis_db_path=tmp_path / "mock.db"))
        _, registry, counts = registry_and_counts("mock")
        app.state.tool_registry = registry
        app.state.agent = AgentOrchestrator(TargetLLM(), registry)
    registry = app.state.tool_registry
    original = registry._specs["dns_lookup"]
    registry._specs["dns_lookup"] = replace(original, handler=lambda **_: ToolResult(
        success=True, tool="dns_lookup", summary="测试 DNS 失败", data=DNSLookupData(resolved=False), duration_ms=1,
    ))
    with TestClient(app) as client:
        owner = register_test_user(client)
        sid = client.post("/api/session").json()["session_id"]
        if subject == "netpilot_host":
            success(client.patch("/api/session/diagnostic-target", json={"session_id": sid, "subject": subject}))
        question = "我的微信能用，但是网页打不开，帮我检查一下。"
        body = complete_sse(client.post("/api/chat/stream", json={"session_id": sid, "message": question}))
        action = body["next_chat_action"]
        assert action["type"] == "remediation_step", body
        assert action == public_action(client, sid) and action["target_subject"] == subject
        registry._specs["dns_lookup"] = original
        yield app, client, owner, sid, counts, body


def test_act_14b_01_remediation_schema():
    *_, task = remote_cycle()
    action = build_next_chat_action(task)
    assert isinstance(action, RemediationStepAction)
    assert action.plan_id == task.remediation_plan.plan_id
    assert action.plan_version == task.remediation_plan.plan_version
    assert action.step_id == task.remediation_plan.steps[0].step_id
    assert action.session_id == task.session_id and action.task_version == task.task_version
    parsed(action)


def test_act_14b_02_verification_schema():
    *_, task = host_cycle()
    action = build_next_chat_action(task)
    assert isinstance(action, VerificationAction) and action.mode == "start"
    values = parsed(action)
    for changes in ({"mode": "arbitrary"}, {"tool_name": "dns_lookup"}, {"arguments": {}}):
        with pytest.raises(ValidationError):
            ADAPTER.validate_python({**values, **changes})


def test_act_14b_03_resolution_schema():
    *_, task = finished()
    action = build_next_chat_action(task)
    assert isinstance(action, ResolutionConfirmationAction)
    assert [(choice.value, choice.label) for choice in action.choices] == list(RESOLUTION_CHOICES)
    values = parsed(action)
    for changes in ({"question": "自定义问题"}, {"type": "other"}, {"authorization": "private"}, {"choices": []}):
        with pytest.raises(ValidationError):
            ADAPTER.validate_python({**values, **changes})


@pytest.mark.parametrize(("factory", "fields"), [
    (remote_cycle, ["step_id", "plan_version", "task_version", "target_version"]),
    (host_cycle, ["verification_id", "plan_version", "task_version", "target_version"]),
    (finished, ["verification_id", "resolution_state_version", "task_version", "target_version"]),
])
def test_act_14b_04_action_id_stability(factory, fields):
    *_, task = factory()
    original = build_next_chat_action(task)
    assert original == build_next_chat_action(task.model_copy(deep=True))
    for field in fields:
        draft = task.model_copy(deep=True)
        plan = draft.remediation_plan
        cycle = draft.verification_cycles[-1]
        resolution = draft.resolution
        if original.type == "resolution_confirmation":
            cycle.status = "inconclusive"
        if field == "step_id":
            plan.steps[0].step_id = uuid4()
        elif field == "plan_version":
            plan.plan_version += 1
            cycle.remediation_plan_version = plan.plan_version
        elif field == "verification_id":
            cycle.verification_id = uuid4()
            resolution.based_on_verification_id = cycle.verification_id
        elif field == "resolution_state_version":
            resolution.state_version += 1
        elif field == "task_version":
            draft.task_version += 1
            resolution.task_version = draft.task_version
            plan.task_version = draft.task_version
            cycle.after_task_version = draft.task_version
        else:
            draft.diagnostic_target.target_version += 1
            resolution.target_version = plan.target_version = cycle.target_version = draft.diagnostic_target.target_version
        updated = build_next_chat_action(draft)
        assert updated.type == original.type and updated.action_id != original.action_id


def test_act_14b_05_safe_pending_selection():
    *_, task = remote_cycle()
    plan = task.remediation_plan
    template = plan.steps[0]
    cases = [{"status": "completed"}, {"status": "skipped"}, {"risk": "medium"}, {"risk": "high"},
             {"requires_admin": True}, {}, {}]
    plan.steps = [template.model_copy(update={"step_id": uuid4(), "order": index, "equivalence_key": f"test-{index}", **flags})
                  for index, flags in enumerate(cases, 1)]
    assert build_next_chat_action(task).step_id == plan.steps[5].step_id
    task.resolution.state = "escalated"
    assert build_next_chat_action(task) is None


def test_act_14b_06_step_lifecycle(remote):
    _, client, _, sid, counts = remote
    action = public_action(client, sid)
    result = success(step_feedback(client, action))
    assert result["remediation_plan"]["steps"][0]["status"] == "completed"
    assert result["verification_cycles"][-1]["status"] == "awaiting_after_evidence"
    assert result["task_version"] == action["task_version"] + 1
    assert_stale(step_feedback(client, action))
    assert sum(counts.values()) == 0


@pytest.mark.parametrize("status", ["awaiting_after_evidence", "verifying"])
def test_act_14b_07_active_cycle_blocks_next_step(status):
    *_, task = waiting_cycle()
    task.verification_cycles[-1].status = status
    task.client_check.declined = ClientCheckScope(task_version=task.task_version, target_version=task.diagnostic_target.target_version)
    assert any(step.status == "pending" for step in task.remediation_plan.steps)
    assert build_next_chat_action(task) is None


def test_act_14b_08_remote_recheck_priority(remote):
    _, client, _, sid, _ = remote
    result = success(step_feedback(client, public_action(client, sid)))
    check = result["next_chat_action"]
    assert (check["type"], check["mode"]) == ("client_check", "recheck")
    assert check == public_action(client, sid)


def test_act_14b_09_supported_readonly_verification(diagnostic_workflow):
    _, client, _, sid, counts, body = diagnostic_workflow
    updated = success(step_feedback(client, body["next_chat_action"]))
    verification = updated["next_chat_action"]
    assert verification == public_action(client, sid)
    assert verification["type"] == "verification" and sum(counts.values()) == 0
    result = success(start_verification(client, verification))
    cycle = result["verification_cycles"][-1]
    assert cycle["status"] == "completed" and cycle["result"] == "improved"
    assert cycle["baseline"]["source_kind"] == cycle["after"]["source_kind"]
    assert sum(counts.values()) == counts["dns_lookup"] == 1
    assert_stale(start_verification(client, verification))
    assert sum(counts.values()) == 1


def test_act_14b_10_demo_exclusion():
    for factory in (waiting_cycle, host_cycle):
        *_, task = factory()
        task.is_demo = True
        cycle = task.verification_cycles[-1]
        assert build_next_chat_action(task) is None
        assert cycle.status == "awaiting_after_evidence" and cycle.after is None


def test_act_14b_11_confirmation_is_current_and_unanswered():
    from netpilot.verification.models import UserVerificationObservation

    *_, task = finished()
    action = build_next_chat_action(task)
    assert action.type == "resolution_confirmation"
    for change in ("feedback", "resolution", "target", "cycle"):
        draft = task.model_copy(deep=True)
        if change == "feedback":
            draft.verification_cycles[-1].user_observation = UserVerificationObservation(symptom_status="unknown")
        elif change == "resolution":
            draft.resolution.user_confirmation = "not_resolved"
        elif change == "target":
            draft.diagnostic_target.target_version += 1
        else:
            draft.verification_cycles[-1].verification_id = uuid4()
        candidate = build_next_chat_action(draft)
        assert candidate is None or candidate.type != "resolution_confirmation"


def test_act_14b_12_stale_step_is_atomic(remote):
    app, client, owner, sid, _ = remote
    action = public_action(client, sid)
    before = app.state.sessions.task_state(UUID(sid), owner)
    assert_stale(step_feedback(client, action, plan_version=action["plan_version"] + 1))
    assert_stale(step_feedback(client, {**action, "step_id": str(uuid4())}))
    assert app.state.sessions.task_state(UUID(sid), owner) == before


def test_act_14b_13_stale_verification_runs_no_tools(diagnostic_workflow):
    app, client, owner, sid, counts, body = diagnostic_workflow
    action = success(step_feedback(client, body["next_chat_action"]))["next_chat_action"]
    app.state.sessions.advance_task_version(UUID(sid), owner)
    before = app.state.sessions.task_state(UUID(sid), owner)
    assert_stale(start_verification(client, action))
    assert app.state.sessions.task_state(UUID(sid), owner) == before and sum(counts.values()) == 0


def remote_after(client, sid, snapshot="valid"):
    success(step_feedback(client, public_action(client, sid)))
    return success(upload(client, sid, payload(snapshot)))


def test_act_14b_14_stale_confirmation_preserves_state(remote):
    app, client, owner, sid, _ = remote
    action = remote_after(client, sid)["next_chat_action"]
    before = app.state.sessions.task_state(UUID(sid), owner)
    assert_stale(confirm(client, action, resolution_state_version=action["resolution_state_version"] + 1))
    assert_stale(confirm(client, action, verification_id=str(uuid4())))
    assert app.state.sessions.task_state(UUID(sid), owner) == before


def test_act_14b_15_resolution_route_response(remote):
    _, client, _, sid, _ = remote
    action = remote_after(client, sid)["next_chat_action"]
    response = confirm(client, action)
    result = success(response)
    fields = {"next_chat_action", "remediation_plan", "verification_cycles", "resolution", "task_version", "diagnostic_target"}
    assert fields <= result.keys() and response.headers["cache-control"] == "no-store"
    assert result["resolution"]["state"] == "resolved" and result["next_chat_action"] is None
    assert result["verification_cycles"][-1]["user_observation"]["symptom_status"] == "resolved_by_user_report"
    restored = client.get("/api/session/resolution", params={"session_id": sid})
    assert restored.headers["cache-control"] == "no-store"
    assert {key: success(restored)[key] for key in fields} == {key: result[key] for key in fields}


def test_act_14b_16_subjective_cannot_resolve_abnormal_metrics(remote):
    _, client, _, sid, _ = remote
    result = remote_after(client, sid, "dns_failure")
    checks = result["verification_cycles"][-1]["checks"]
    confirmed = success(confirm(client, result["next_chat_action"]))
    assert confirmed["resolution"]["state"] != "resolved"
    assert confirmed["resolution"]["user_confirmation"] == "resolved"
    assert confirmed["verification_cycles"][-1]["checks"] == checks


def test_act_14b_17_unknown_confirmation_consumed(remote):
    _, client, _, sid, _ = remote
    action = remote_after(client, sid)["next_chat_action"]
    result = success(confirm(client, action, status="unknown"))
    assert result["verification_cycles"][-1]["user_observation"]["symptom_status"] == "unknown"
    restored = public_action(client, sid)
    assert restored == result["next_chat_action"]
    assert restored is None or restored["type"] != "resolution_confirmation"
    assert_stale(confirm(client, action, status="unknown"))


def test_act_14b_18_legacy_and_partial_metadata(remote):
    _, client, _, sid, _ = remote
    action = public_action(client, sid)
    step_url = f"/api/session/remediation-plan/steps/{action['step_id']}"
    payload_data = {"session_id": sid, "action": "complete"}
    assert client.patch(step_url, json={**payload_data, "action_id": action["action_id"]}).status_code == 422
    cycle = success(client.patch(step_url, json=payload_data))["verification_cycles"][-1]
    start_url = f"/api/session/verification/{cycle['verification_id']}/start"
    assert client.post(start_url, json={"session_id": sid, "plan_version": 1}).status_code == 422
    success(client.post(start_url, json={"session_id": sid}))
    success(upload(client, sid, payload()))
    confirm_body = {"session_id": sid, "status": "resolved"}
    assert client.post("/api/session/resolution/confirm", json={**confirm_body, "resolution_state_version": 1}).status_code == 422
    assert success(client.post("/api/session/resolution/confirm", json=confirm_body))["resolution"]["state"] == "resolved"


def test_act_14b_19_failed_persistence_keeps_all_workflow_state(remote, monkeypatch):
    app, client, owner, sid, _ = remote

    def fail(*args):
        raise DiagnosisStorageError("private storage error")

    with monkeypatch.context() as patch:
        patch.setattr(app.state.diagnosis_repository, "update_remediation", fail)
        before = app.state.sessions.task_state(UUID(sid), owner)
        assert step_feedback(client, public_action(client, sid)).status_code == 503
        assert app.state.sessions.task_state(UUID(sid), owner) == before
    action = remote_after(client, sid)["next_chat_action"]
    before = app.state.sessions.task_state(UUID(sid), owner)
    monkeypatch.setattr(app.state.diagnosis_repository, "update_resolution", fail)
    assert confirm(client, action).status_code == 503
    assert app.state.sessions.task_state(UUID(sid), owner) == before


def test_act_14b_20_conversation_uses_no_fake_turns(diagnostic_workflow):
    app, client, owner, sid, _, body = diagnostic_workflow
    verification = success(step_feedback(client, body["next_chat_action"]))["next_chat_action"]
    confirmation = success(start_verification(client, verification))["next_chat_action"]
    assert confirmation["type"] == "resolution_confirmation"
    final = success(confirm(client, confirmation))
    assert final["resolution"]["state"] == "resolved"
    record = success(client.get(f"/api/diagnoses/{body['record_id']}"))
    assert record["turn_count"] == app.state.sessions.task_state(UUID(sid), owner).turn_index == 1
    assert len(app.state.sessions.history(UUID(sid), owner)) == 2
