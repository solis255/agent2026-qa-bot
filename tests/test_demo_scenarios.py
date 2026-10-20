"""12I acceptance: all outcomes follow authenticated production API paths."""
import ast
import json
from pathlib import Path
import socket
import sqlite3
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from conftest import register_test_user
from netpilot.config import Settings
from netpilot.main import create_app
from netpilot.demo.acceptance import checked, chat, load, run_scenario
from netpilot.demo.runtime import FIXTURE_ROOT
from netpilot.demo.scenarios import SCENARIOS
from netpilot.client_snapshot.validation import parse_snapshot
from netpilot.history import SQLiteDiagnosisRepository


@pytest.fixture
def demo(tmp_path):
    app = create_app(Settings(_env_file=None, demo_mode=True, tju_api_key=None, rag_enabled=False,
        tool_mode="mock", diagnosis_history_enabled=True, diagnosis_db_path=tmp_path / "demo.db"))
    with TestClient(app) as client:
        owner = register_test_user(client)
        yield app, client, owner


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_ds01_ds06_complete_production_journeys(demo, scenario):
    app, client, owner = demo
    result = run_scenario(client, scenario)
    runtime = app.state.demo_manager.require(UUID(result["session_id"]), owner)
    task = runtime.sessions.task_state(runtime.session_id, owner)
    assert runtime.tools.handler_calls == 0
    if scenario.startswith("dns_"):
        assert any(h.name == "dns_resolution_path_failure" and h.status == "supported" for h in task.hypotheses) or scenario == "dns_recovery"


@pytest.mark.parametrize("path", sorted(FIXTURE_ROOT.glob("*.json")), ids=lambda p: p.stem)
def test_schema_valid_deterministic_fixtures(path):
    first, digest = parse_snapshot(path.read_bytes())
    second, another = parse_snapshot(path.read_bytes())
    assert first == second and digest == another
    assert first.redaction.secrets_removed


def test_ds07_ds08_host_tools_blocked_and_evidence_isolated(demo):
    app, client, owner = demo
    normal = checked(client.post("/api/session"))["session_id"]
    original = app.state.sessions.task_state(UUID(normal), owner).model_dump()
    sid = checked(client.post("/api/demo/session", json={"scenario_id": "dns_recovery"}))["session_id"]
    runtime = app.state.demo_manager.require(UUID(sid), owner)
    result = runtime.registry.execute("dns_lookup", '{"domain":"www.tju.edu.cn"}', target=runtime.sessions.task_state(UUID(sid), owner).diagnostic_target)
    assert result.result.error.code.value == "security_blocked" and runtime.tools.handler_calls == 0
    loaded = load(client, sid, "dns_recovery_before")
    assert all(e["target_subject"] == "user_client" and e["execution_scope"] == "client_snapshot" for e in loaded["client_evidence"])
    assert app.state.sessions.task_state(UUID(normal), owner).model_dump() == original


def test_ds10_history_restore_after_runtime_and_repository_restart(demo):
    app, client, owner = demo
    result = run_scenario(client, "dns_recovery")
    repository = SQLiteDiagnosisRepository(app.state.settings.diagnosis_db_path)
    record = repository.get(owner, UUID(result["record_id"]))
    assert record.is_demo and record.demo_scenario_id == "dns_recovery"
    assert record.resolution.state == "resolved" and record.conversation_complete
    assert record.client_evidence and record.remediation_plan and record.verification_cycles and record.reasoning_trace
    assert not repository.query_context_records(owner), "Demo data must not enter real historical analysis"


def test_ds11_reset_preserves_history_and_normal_sessions(demo):
    app, client, owner = demo
    normal = checked(client.post("/api/session"))["session_id"]
    result = run_scenario(client, "dns_recovery")
    old_sid = result["session_id"]
    new = checked(client.post(f"/api/demo/session/{old_sid}/reset"))
    assert new["session_id"] != old_sid and not new["client_evidence"]
    assert checked(client.get(f"/api/session/{normal}"))["is_demo"] is False
    assert checked(client.get(f'/api/diagnoses/{result["record_id"]}'))["resolution"]["state"] == "resolved"
    assert client.get(f"/api/session/{old_sid}").status_code == 404


def test_ds12_two_users_are_independent_and_legacy_switch_cannot_clear_demo(demo):
    app, alice, _ = demo
    a = checked(alice.post("/api/demo/session", json={"scenario_id": "dns_recovery"}))["session_id"]
    load(alice, a, "dns_recovery_before")
    with TestClient(app) as bob:
        register_test_user(bob)
        b = checked(bob.post("/api/demo/session", json={"scenario_id": "single_service"}))["session_id"]
        load(bob, b, "single_service")
        assert checked(bob.get(f"/api/session/{b}"))["client_evidence"][1]["status"] == "normal"
        assert checked(alice.get(f"/api/session/{a}"))["client_evidence"][1]["status"] == "abnormal"
        checked(bob.post(f"/api/demo/session/{b}/reset"))
        assert checked(alice.get(f"/api/session/{a}"))["client_snapshot_summary"]["snapshot_sequence"] == 1
        app.state.sessions.clear()  # Existing singleton controls only own normal sessions.
        assert alice.get(f"/api/session/{a}").status_code == 200


def test_ds13_offline_no_dns_http_or_llm_network_needed(demo, monkeypatch):
    def network_forbidden(*args, **kwargs): raise AssertionError("unexpected external network")
    monkeypatch.setattr(socket, "getaddrinfo", network_forbidden)
    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    result = run_scenario(demo[1], "dns_recovery")
    assert result["status"]["metrics"]["llm_calls"] == 0


def test_ds14_loader_uses_formal_parser_and_no_final_state_injection(demo, monkeypatch):
    import netpilot.demo.runtime as runtime_module
    from netpilot.client_snapshot.validation import SnapshotValidationError
    app, client, _ = demo
    sid = checked(client.post("/api/demo/session", json={}))["session_id"]
    def reject(*args, **kwargs): raise SnapshotValidationError("controlled_rejection")
    monkeypatch.setattr(runtime_module, "parse_snapshot", reject)
    assert client.post(f"/api/demo/session/{sid}/load-snapshot/dns_recovery_before").status_code == 422
    assert not checked(client.get(f"/api/session/{sid}"))["client_evidence"]
    for name in ["runtime.py", "acceptance.py"]:
        tree = ast.parse((Path(runtime_module.__file__).parent / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert not any(isinstance(t, ast.Attribute) and t.attr in {"resolution", "evidence", "diagnosis", "state"} for t in targets)


def test_ds15_observability_allowlist_no_prompts_or_raw_payload(demo):
    client = demo[1]
    sid = checked(client.post("/api/demo/session", json={}))["session_id"]
    body = checked(client.get(f"/api/demo/session/{sid}"))
    assert set(body).isdisjoint({"system_prompt", "messages", "raw_snapshot", "reasoning", "cot", "raw_result"})
    assert body["is_demo"] and "metrics" in body


def test_ds16_privacy_still_rejects_sensitive_uploaded_fields(demo):
    from client_snapshot_helpers import upload
    client = demo[1]
    sid = checked(client.post("/api/demo/session", json={}))["session_id"]
    value = json.loads((FIXTURE_ROOT / "dns_recovery_before.json").read_text(encoding="utf-8"))
    value["password"] = "never-store-this"
    response = upload(client, sid, value)
    assert response.status_code == 422 and "never-store-this" not in response.text


def test_ds17_auth_and_disabled_feature(demo, tmp_path):
    app, _, _ = demo
    with TestClient(app) as anon:
        assert anon.get("/api/demo/scenarios").status_code == 401
        assert anon.post("/api/demo/session", json={}).status_code == 401
    off = create_app(Settings(_env_file=None, demo_mode=False, rag_enabled=False, diagnosis_history_enabled=False, diagnosis_db_path=tmp_path / "off.db"))
    with TestClient(off) as client:
        register_test_user(client)
        assert client.get("/api/demo/scenarios").status_code == 404
        assert client.post("/api/demo/session", json={}).status_code == 404
        assert client.get("/api/health").json()["demo_mode"] is False


@pytest.mark.parametrize("action", ["status", "reset", "fixture", "select", "regular_session", "remediation", "chat"])
def test_ds18_ownership(demo, action):
    app, alice, _ = demo
    sid = checked(alice.post("/api/demo/session", json={}))["session_id"]
    with TestClient(app) as bob:
        register_test_user(bob)
        calls = {
            "status": lambda: bob.get(f"/api/demo/session/{sid}"),
            "reset": lambda: bob.post(f"/api/demo/session/{sid}/reset"),
            "fixture": lambda: bob.post(f"/api/demo/session/{sid}/load-snapshot/dns_recovery_before"),
            "select": lambda: bob.post(f"/api/demo/session/{sid}/scenario/single_service"),
            "regular_session": lambda: bob.get(f"/api/session/{sid}"),
            "remediation": lambda: bob.post("/api/session/remediation-plan", json={"session_id": sid}),
            "chat": lambda: bob.post("/api/chat", json={"session_id": sid, "message": "网页打不开"}),
        }
        assert calls[action]().status_code == 404


def test_ds20_normal_session_behavior_and_input_authority_unchanged(demo):
    app, client, _ = demo
    normal = checked(client.post("/api/session"))
    assert normal["is_demo"] is False and normal["diagnostic_target"]["subject"] == "mock_client"
    assert client.post("/api/chat", json={"session_id": normal["session_id"], "message": "诊断"}).status_code == 503
    assert client.post("/api/demo/session", json={"scenario_id": "dns_recovery", "resolution": "resolved"}).status_code == 422


def test_loader_order_duplicates_and_rollback(demo):
    client = demo[1]
    sid = checked(client.post("/api/demo/session", json={}))["session_id"]
    assert client.post(f"/api/demo/session/{sid}/load-snapshot/dns_recovery_after").status_code == 409
    first = load(client, sid, "dns_recovery_before")
    second = load(client, sid, "dns_recovery_before")
    assert second["duplicate"] and first["client_snapshot_summary"] == second["client_snapshot_summary"]
    assert client.post(f"/api/demo/session/{sid}/load-snapshot/privacy_case").status_code == 404


def test_llm_failure_cannot_break_structured_demo(demo):
    from netpilot.llm.errors import LLMResponseError
    app, client, owner = demo
    sid = checked(client.post("/api/demo/session", json={}))["session_id"]
    load(client, sid, "dns_recovery_before")
    chat(client, sid, "网页打不开，请分析快照")
    checked(client.post("/api/session/remediation-plan", json={"session_id": sid}))
    before = checked(client.get(f"/api/session/{sid}"))
    runtime = app.state.demo_manager.require(UUID(sid), owner)
    class FailingLLM:
        def chat(self, *args, **kwargs): raise LLMResponseError("token=private-error")
    runtime.llm_metrics.client = FailingLLM()
    failed = chat(client, sid, "你好")
    assert "private-error" not in json.dumps(failed)
    after = checked(client.get(f"/api/session/{sid}"))
    assert [e["evidence_id"] for e in after["client_evidence"]] == [e["evidence_id"] for e in before["client_evidence"]]
    assert after["remediation_plan"]["plan_id"] == before["remediation_plan"]["plan_id"]
