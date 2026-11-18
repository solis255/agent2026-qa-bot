"""Milestone 14A: API actions, replay protection and transport parity."""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from client_snapshot_helpers import payload, upload
from conftest import register_test_user
from netpilot.chat_actions.factory import build_next_chat_action
from netpilot.chat_actions.models import ChatAction, ClientCheckChatAction, ContextQuestionAction
from netpilot.conversation_context.questions import build_context_question
from test_adaptive_diagnostic_flow import WINDOWS_WEB
from test_context_acquisition import complete_sse, context_app, send


ADAPTER = TypeAdapter(ChatAction)
SCOPE = {
    "schema_version": 1, "session_id": str(uuid4()), "action_id": str(uuid4()),
    "task_version": 3, "target_subject": "user_client", "target_version": 2,
}
QUESTION = {**SCOPE, **build_context_question("network_access").model_dump()}
CHECK = {**SCOPE, "type": "client_check", "mode": "initial", "reason": "current_client_evidence_missing"}


def current(client, sid):
    response = client.get(f"/api/session/{sid}")
    assert response.status_code == 200, response.text
    return response.json()["next_chat_action"]


def answer_payload(action, value):
    return {**{key: action[key] for key in ("action_id", "task_version", "target_version", "field")}, "value": value}


def submit(client, sid, answer, path="/api/chat"):
    return client.post(path, json={"session_id": sid, "message": "选项回答", "context_answer": answer})


def assert_projection(response):
    action = response["next_chat_action"]
    assert response["ui_action"] == (
        {key: val for key, val in action.items() if key not in (
            {"schema_version", "target_subject"} | (
                {"session_id", "action_id", "task_version", "target_version"} if action["type"] == "context_question" else set()
            )
        )} if action else None
    )
    return action


def test_act_01_context_schema():
    action = ADAPTER.validate_python(QUESTION)
    assert isinstance(action, ContextQuestionAction)
    assert ADAPTER.validate_json(ADAPTER.dump_json(action)) == action
    assert (action.action_id, action.task_version, action.target_version) == (UUID(SCOPE["action_id"]), 3, 2)


@pytest.mark.parametrize("mode", ["initial", "recheck"])
def test_act_02_client_check_schema(mode):
    action = ADAPTER.validate_python({**CHECK, "mode": mode})
    assert isinstance(action, ClientCheckChatAction)
    assert (action.mode, action.platform, action.target_subject) == (mode, "windows", "user_client")
    for invalid in ({"platform": "macos"}, {"target_subject": "netpilot_host"}):
        with pytest.raises(ValidationError):
            ADAPTER.validate_python({**CHECK, **invalid})


@pytest.mark.parametrize("invalid", [
    {key: value for key, value in QUESTION.items() if key != missing} for missing in ("action_id", "task_version")
] + [
    {**QUESTION, "target_version": 0},
    {**QUESTION, "schema_version": True},
    {**QUESTION, "task_version": "3"},
    {**CHECK, "target_version": "2"},
    {**QUESTION, "type": "unknown"},
    {**QUESTION, "snapshot": {}},
    {**QUESTION, "question": "https://example.invalid"},
    {**QUESTION, "choices": [{"value": "campus_wifi", "label": "C:/diagnostics"}]},
])
def test_act_03_invalid_action(invalid):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(invalid)


def test_act_04_stable_context_action_id(context_app):
    app, client, owner, sid, *_ = context_app
    first = send(client, sid, "校园网连不上")["next_chat_action"]
    task = app.state.sessions.task_state(UUID(sid), owner)
    assert build_next_chat_action(task).action_id == UUID(first["action_id"])
    for scope in ("task_version", "target_version"):
        draft = task.model_copy(deep=True)
        subject = draft if scope == "task_version" else draft.diagnostic_target
        setattr(subject, scope, getattr(subject, scope) + 1)
        setattr(draft.context_acquisition, scope, getattr(subject, scope))
        setattr(draft.last_diagnostic_readiness, scope, getattr(subject, scope))
        assert build_next_chat_action(draft).action_id != UUID(first["action_id"])
    second = submit(client, sid, answer_payload(first, "all_network")).json()["next_chat_action"]
    assert second["field"] == "network_access" and second["action_id"] != first["action_id"]


def test_act_05_chat_response(context_app):
    _, client, _, sid, *_ = context_app
    assert assert_projection(send(client, sid, "eduroam 是什么？")) is None
    assert assert_projection(send(client, sid, "网页打不开"))["type"] == "context_question"


def test_act_06_client_check(context_app):
    _, client, _, sid, tools, _ = context_app
    action = assert_projection(send(client, sid, WINDOWS_WEB))
    assert (action["type"], action["mode"], action["target_subject"]) == ("client_check", "initial", "user_client")
    assert action == current(client, sid)
    assert tools.handler_calls == 0


def test_act_07_demo_exclusion(context_app):
    app, client, owner, _, *_ = context_app
    sid = str(app.state.sessions.create(owner, is_demo=True).session_id)
    response = send(client, sid, WINDOWS_WEB)
    assert response["diagnostic_readiness"]["state"] == "need_client_evidence"
    assert assert_projection(response) is None and current(client, sid) is None
    ordinary = str(app.state.sessions.create(owner).session_id)
    action = send(client, ordinary, WINDOWS_WEB)["next_chat_action"]
    assert upload(client, sid, payload(), headers=check_headers(action)).status_code == 409


def test_act_08_session_restore_and_consumption(context_app):
    _, client, _, sid, *_ = context_app
    first = send(client, sid, "网页打不开")
    action = assert_projection(first)
    client.patch("/api/session/environment/browser", json={"session_id": sid, "browser_online": True}).raise_for_status()
    assert current(client, sid) == action
    client.patch("/api/session/environment/user", json={"session_id": sid, "affected_scope": "web_only"}).raise_for_status()
    assert current(client, sid) is None
    assert submit(client, sid, answer_payload(action, "all_network")).status_code == 409

    other = client.post("/api/session").json()["session_id"]
    pending = send(client, other, "网页打不开")["next_chat_action"]
    response = submit(client, other, answer_payload(pending, "unknown"))
    assert response.status_code == 200 and response.json()["next_chat_action"] is None
    assert current(client, other) is None
    assert submit(client, other, answer_payload(pending, "all_network")).status_code == 409


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
@pytest.mark.parametrize("change", ["task", "target", "wrong_id", "other_session"])
def test_act_09_stale_context_action(context_app, path, change):
    app, client, owner, sid, *_ = context_app
    action = send(client, sid, "网页打不开")["next_chat_action"]
    reply = answer_payload(action, "web_only")
    if change == "task":
        app.state.sessions.advance_task_version(UUID(sid), owner)
    elif change == "target":
        client.patch("/api/session/diagnostic-target", json={"session_id": sid, "subject": "netpilot_host"}).raise_for_status()
    elif change == "wrong_id":
        reply["action_id"] = str(uuid4())
    else:
        sid = client.post("/api/session").json()["session_id"]
        send(client, sid, "网页打不开")
    before = app.state.sessions.task_state(UUID(sid), owner)
    response = submit(client, sid, reply, path)
    assert response.status_code == 409
    assert response.json()["detail"] == "这个操作已经过期，请根据当前对话继续。"
    assert app.state.sessions.task_state(UUID(sid), owner) == before
    assert not app.state.sessions.get(UUID(sid), owner).busy


@pytest.mark.parametrize("key", ["action_id", "task_version", "target_version"])
def test_act_10_partial_metadata(context_app, key):
    _, client, _, sid, *_ = context_app
    action = send(client, sid, "网页打不开")["next_chat_action"]
    answer = {"field": action["field"], "value": "web_only", key: action[key]}
    assert submit(client, sid, answer).status_code == 422
    assert current(client, sid) == action


def test_act_11_legacy_compatibility_and_owner(context_app):
    app, client, _, sid, *_ = context_app
    first = send(client, sid, "网页打不开")
    assert assert_projection(first)["field"] == "affected_scope"
    answer = {"field": "affected_scope", "value": "unknown"}
    other = TestClient(app)
    register_test_user(other)
    assert submit(other, sid, answer).status_code == 404
    assert other.get(f"/api/session/{sid}").status_code == 404
    assert submit(client, sid, {"field": "network_access", "value": "campus_wifi"}).status_code == 409
    assert submit(client, sid, answer).status_code == 200
    assert submit(client, sid, answer).status_code == 409


@pytest.mark.parametrize("message", ["网页打不开", WINDOWS_WEB, "eduroam 是什么？"])
def test_act_12_sse_contract(context_app, message):
    _, client, _, sid, *_ = context_app
    other = client.post("/api/session").json()["session_id"]
    plain = assert_projection(send(client, sid, message))
    streamed = assert_projection(complete_sse(client.post("/api/chat/stream", json={"session_id": other, "message": message})))
    assert plain == current(client, sid) and streamed == current(client, other)
    if plain is not None:
        assert streamed is not None
        assert (plain["session_id"], streamed["session_id"]) == (sid, other)
        assert plain["action_id"] != streamed["action_id"]
        assert {k: v for k, v in plain.items() if k not in {"session_id", "action_id"}} == {
            k: v for k, v in streamed.items() if k not in {"session_id", "action_id"}
        }
    else:
        assert streamed is None


def check_headers(action):
    return {"X-NetPilot-Check-ID": action["action_id"], "X-NetPilot-Task-Version": str(action["task_version"]),
            "X-NetPilot-Target-Version": str(action["target_version"])}


def test_old_client_check_and_file_do_not_cross_manual_network_change(context_app):
    app, client, owner, sid, *_ = context_app
    action = send(client, sid, WINDOWS_WEB)["next_chat_action"]
    old_result = payload()
    uploaded = upload(client, sid, old_result, headers=check_headers(action))
    uploaded.raise_for_status()
    receipt = uploaded.json()["client_check_continuation"]
    assert receipt
    client.patch("/api/session/environment/user", json={"session_id": sid, "network_access": "campus_wired"}).raise_for_status()
    assert current(client, sid) is None
    assert upload(client, sid, old_result, headers=check_headers(action)).status_code == 409
    assert client.post("/api/chat", json={"session_id": sid, "continuation": "client_evidence_uploaded",
                                        "continuation_id": receipt["receipt_id"]}).status_code == 409
    archived = upload(client, sid, old_result).json()
    assert archived["client_evidence"] and not archived["client_snapshot_summary"]["applicable"]
    assert archived["client_check_continuation"] is None
    assert not app.state.sessions.task_state(UUID(sid), owner).reusable_evidence()
