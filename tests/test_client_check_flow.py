import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from client_snapshot_helpers import payload, upload
from conftest import register_test_user
from test_context_acquisition import context_app, send, complete_sse
from test_adaptive_diagnostic_flow import WINDOWS_WEB
from netpilot.client_snapshot.check_models import ClientCheckAction


def continue_check(client,sid,receipt,*,stream=False):
    body={"session_id":sid,"continuation":"client_evidence_uploaded","continuation_id":receipt["receipt_id"]}
    response=client.post("/api/chat/stream" if stream else "/api/chat",json=body)
    return complete_sse(response) if stream else response


def test_initial_action_strict_union_and_session_binding(context_app):
    _,client,_,sid,tools,_=context_app
    result=send(client,sid,WINDOWS_WEB)
    action=result["ui_action"]
    assert action["type"] == "client_check" and action["mode"] == "initial"
    assert action["session_id"] == sid and action["task_version"] == action["target_version"] == 1
    assert action["platform"] == "windows" and action["collector_supported"] and action["upload_required"]
    assert client.get(f"/api/session/{sid}").json()["ui_action"] == action
    with pytest.raises(ValidationError): ClientCheckAction(**action,local_path="C:/secret")
    assert tools.handler_calls == 0


@pytest.mark.parametrize("message,expected",[("eduroam 是什么？",None),("网页打不开","context_question"),(WINDOWS_WEB.replace("Windows","macOS"),None)])
def test_other_routes_do_not_get_windows_action(context_app,message,expected):
    _,client,_,sid,_,_=context_app
    result=send(client,sid,message)
    assert (result["ui_action"]["type"] if result["ui_action"] else None) == expected


def test_decline_persists_for_phase_and_explicit_reopen(context_app):
    app,client,owner,sid,tools,_=context_app
    action=send(client,sid,WINDOWS_WEB)["ui_action"]
    body={k:action[k] for k in ("session_id","action_id","task_version","target_version")}
    response=client.post("/api/session/client-check/decline",json=body)
    assert response.status_code == 200 and response.json()["client_check_declined"]
    for text in ["那怎么办？",WINDOWS_WEB]:
        result=send(client,sid,text)
        assert result["ui_action"] is None and "暂时不做" in result["answer"]
    assert not app.state.sessions.task_state(UUID(sid),owner).evidence
    reopened=send(client,sid,"现在可以检查")
    assert reopened["ui_action"]["type"] == "client_check"
    assert not app.state.sessions.task_state(UUID(sid),owner).client_check.declined and tools.handler_calls == 0


def test_decline_old_action_or_other_owner_is_rejected(context_app):
    app,client,_,sid,_,_=context_app
    action=send(client,sid,WINDOWS_WEB)["ui_action"]
    body={k:action[k] for k in ("session_id","action_id","task_version","target_version")}
    bob=TestClient(app);register_test_user(bob)
    assert bob.post("/api/session/client-check/decline",json=body).status_code == 404
    send(client,sid,"我现在改用有线网了")
    assert client.post("/api/session/client-check/decline",json=body).status_code == 409
    fresh=send(client,sid,"我用 Windows，所有应用都不能联网")
    assert fresh["ui_action"]["task_version"] == 2


def test_upload_receipt_continuation_uses_real_evidence_and_marks_system_turn(context_app):
    app,client,owner,sid,tools,llm=context_app
    first=send(client,sid,WINDOWS_WEB)
    raw=payload("dns_failure")
    uploaded=upload(client,sid,raw)
    assert uploaded.status_code == 200
    receipt=uploaded.json()["client_check_continuation"]
    assert receipt and uploaded.json()["client_evidence"]
    result=continue_check(client,sid,receipt)
    assert result.status_code == 200,result.text
    body=result.json()
    assert body["turn_origin"] == "system_continuation" and body["ui_action"] is None
    assert body["diagnostic_readiness"]["recommended_action"] == "analyze_existing"
    assert "采集时存在 DNS 解析失败" in body["answer"] and "远程检测了" not in body["answer"]
    record=app.state.diagnosis_repository.get(owner,UUID(first["record_id"]))
    assert record.conversation_turns[-1].turn_origin == "system_continuation"
    assert record.conversation_turns[-1].user_message == "[系统自动继续：网络检查结果已上传]"
    assert record.schema_version == 12 and tools.handler_calls == 0 and not llm.calls
    assert continue_check(client,sid,receipt).status_code == 409
    duplicate=upload(client,sid,raw).json()
    assert duplicate["duplicate"] and duplicate["client_check_continuation"] is None


@pytest.mark.parametrize("mutation",["random","other_session","task_changed","target_changed","replaced","expired"])
def test_forged_stale_or_replayed_continuation_is_rejected_before_busy(context_app,mutation):
    app,client,owner,sid,_,_=context_app
    send(client,sid,WINDOWS_WEB)
    receipt=upload(client,sid,payload()).json()["client_check_continuation"]
    if mutation == "random": receipt["receipt_id"]=str(uuid4())
    if mutation == "other_session": sid=client.post("/api/session").json()["session_id"]
    if mutation == "task_changed": send(client,sid,"我现在改用有线网了")
    if mutation == "target_changed": client.patch("/api/session/diagnostic-target",json={"session_id":sid,"subject":"netpilot_host"})
    if mutation == "replaced": upload(client,sid,payload("dns_failure"))
    if mutation == "expired":
        for item in app.state.sessions._sessions[UUID(sid)].task_state.evidence:
            item.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    result=continue_check(client,sid,receipt)
    assert result.status_code == 409,result.text
    assert not app.state.sessions.get(UUID(sid),owner).busy


@pytest.mark.parametrize("minutes",[-60,60])
def test_stale_or_skew_is_retained_without_continuation(context_app,minutes):
    _,client,_,sid,_,_=context_app
    send(client,sid,WINDOWS_WEB)
    raw=payload();raw["generated_at"]=(datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat()
    result=upload(client,sid,raw).json()
    assert result["client_evidence"] and result["client_check_continuation"] is None
    assert send(client,sid,"检查我的 DNS")["diagnostic_readiness"]["state"] == "need_client_evidence"


def test_continuation_chat_sse_parity(context_app):
    _,client,_,sid,tools,_=context_app
    other=client.post("/api/session").json()["session_id"]
    results=[]
    for identifier,stream in [(sid,False),(other,True)]:
        send(client,identifier,WINDOWS_WEB)
        receipt=upload(client,identifier,payload("dns_failure")).json()["client_check_continuation"]
        result=continue_check(client,identifier,receipt,stream=stream)
        results.append(result if stream else result.json())
    assert results[0]["diagnostic_readiness"] == results[1]["diagnostic_readiness"]
    assert results[0]["turn_origin"] == results[1]["turn_origin"] == "system_continuation"
    assert tools.handler_calls == 0


@pytest.mark.parametrize("value",["anything",True,{"type":"client_evidence_uploaded"}])
def test_continuation_enum_is_strict(context_app,value):
    _,client,_,sid,_,_=context_app
    result=client.post("/api/chat",json={"session_id":sid,"message":"ignored","continuation":value,"continuation_id":str(uuid4())})
    assert result.status_code == 422


def test_recheck_action_and_existing_after_comparator(context_app):
    app,client,owner,sid,tools,_=context_app
    send(client,sid,WINDOWS_WEB)
    before=payload("dns_failure")
    receipt=upload(client,sid,before).json()["client_check_continuation"]
    assert continue_check(client,sid,receipt).status_code == 200
    plan=client.get(f"/api/session/{sid}").json()["remediation_plan"]
    assert plan["status"] != "superseded", plan
    result=client.patch(f'/api/session/remediation-plan/steps/{plan["steps"][0]["step_id"]}',json={"session_id":sid,"action":"complete"})
    assert result.status_code == 200,result.text
    action=result.json()["ui_action"]
    assert action["mode"] == "recheck" and action["task_version"] == 2
    task=app.state.sessions.task_state(UUID(sid),owner)
    old_ids=[e.evidence_id for e in task.evidence]
    duplicate=upload(client,sid,before).json()
    assert duplicate["duplicate"] and duplicate["client_check_continuation"] is None
    assert [e.evidence_id for e in app.state.sessions.task_state(UUID(sid),owner).evidence] == old_ids
    after=upload(client,sid,payload()).json()
    assert after["verification_cycles"][-1]["result"] == "improved"
    assert after["resolution"]["state"] != "resolved"
    continued=continue_check(client,sid,after["client_check_continuation"])
    assert continued.status_code == 200,continued.text
    assert continued.json()["verification_cycles"][-1]["result"] == "improved" and tools.handler_calls == 0


def test_stale_upload_recomputes_readiness_and_allows_decline(context_app):
    _,client,_,sid,_,_=context_app
    action=send(client,sid,WINDOWS_WEB)["ui_action"]
    raw=payload();raw["generated_at"]=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    result=upload(client,sid,raw).json()
    assert result["diagnostic_readiness"]["state"] == "need_client_evidence"
    assert result["client_check_continuation"] is None
    assert client.post("/api/session/client-check/decline",json={k:action[k] for k in ("session_id","action_id","task_version","target_version")}).status_code == 200


def test_old_wizard_upload_cannot_bind_to_new_phase(context_app):
    app,client,owner,sid,_,_=context_app
    action=send(client,sid,WINDOWS_WEB)["ui_action"]
    headers={"X-NetPilot-Check-ID":action["action_id"],"X-NetPilot-Task-Version":str(action["task_version"]),"X-NetPilot-Target-Version":str(action["target_version"])}
    send(client,sid,"我现在改用有线网了")
    before=app.state.sessions.task_state(UUID(sid),owner)
    assert upload(client,sid,payload(),headers=headers).status_code == 409
    assert app.state.sessions.task_state(UUID(sid),owner) == before
