from uuid import UUID
from fastapi.testclient import TestClient
from target_helpers import local_app
from test_remediation_api import setup_plan
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.models.schemas import DiagnosisRecordView
from netpilot.reports import build_diagnosis_report

BASE="/api/session/escalation-package"


def test_ep19_artifact_durable_before_first_chat_no_fake_history(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=setup_plan(client)
        data=client.post(BASE,json={"session_id":sid}).json();p=data["packages"][-1]
        assert app.state.diagnosis_repository.count(owner)==0
        repo=SQLiteDiagnosisRepository(tmp_path/"target.db")
        assert repo.escalation_packages(owner,UUID(sid))[0].model_dump(mode="json")==p
        app.state.sessions.clear()
        restored=client.get(BASE,params={"session_id":sid}).json()
        assert restored["historical"] and restored["packages"]==data["packages"]
        assert client.get(f'{BASE}/{p["package_id"]}/export',params={"session_id":sid,"format":"json"}).json()==p


def test_ep17_history_chat_sse_versions_old_export_unchanged(tmp_path):
    from client_snapshot_helpers import payload,upload
    app,counts=local_app(tmp_path)
    with TestClient(app) as client:
        owner,sid,_=setup_plan(client)
        data=client.post("/api/chat",json={"session_id":sid,"message":"我要报修"}).json()
        assert data["escalation_packages"],data
        old=data["escalation_packages"][0];rid=data["record_id"]
        record=client.get(f"/api/diagnoses/{rid}").json()
        assert record["escalation_packages"]==[old] and record["turn_count"]==1
        assert upload(client,sid,payload()).status_code==200
        status=client.get(BASE,params={"session_id":sid}).json()
        assert old["package_id"] in status["stale_package_ids"]
        stream=client.post("/api/chat/stream",json={"session_id":sid,"message":"帮我生成报修材料"})
        assert stream.status_code==200 and "已生成报修材料" in stream.text
        record=client.get(f"/api/diagnoses/{rid}").json()
        assert len(record["escalation_packages"])==2 and record["turn_count"]==2
        assert record["escalation_packages"][0]==old and record["escalation_packages"][-1]["package_version"]==2
        assert client.get(f'{BASE}/{old["package_id"]}/export',params={"session_id":sid,"format":"json"}).json()==old
        restored=SQLiteDiagnosisRepository(tmp_path/"target.db").get(owner,UUID(rid))
        assert build_diagnosis_report(restored).escalation_packages==restored.escalation_packages
        assert sum(counts.values())==0


def test_legacy_history_defaults_empty(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,_=setup_plan(client)
        data=client.post("/api/chat",json={"session_id":sid,"message":"生成诊断报告"}).json()
        record=client.get(f'/api/diagnoses/{data["record_id"]}').json()
        record.pop("escalation_packages");record["schema_version"]=10
        assert DiagnosisRecordView.model_validate(record).escalation_packages==[]


def test_duplicate_chat_material_requests_do_not_create_new_packages_or_traces(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        _,sid,_=setup_plan(client)
        first=client.post("/api/chat",json={"session_id":sid,"message":"我要报修"}).json()
        second=client.post("/api/chat",json={"session_id":sid,"message":"帮我生成报修材料"}).json()
        assert second["escalation_packages"]==first["escalation_packages"]
        assert not [e for e in second["reasoning_trace"] if e["event_origin"]=="escalation"]
        record=client.get(f'/api/diagnoses/{first["record_id"]}').json()
        assert record["turn_count"]==2 and len(record["escalation_packages"])==1
