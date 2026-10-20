"""Reusable API acceptance journeys, with assertions rather than injected outcomes."""
from uuid import UUID


def checked(response):
    assert response.is_success, f"HTTP {response.status_code}: {response.text[:400]}"
    return response.json()


def chat(client, sid, message):
    return checked(client.post("/api/chat", json={"session_id": sid, "message": message}))


def load(client, sid, fixture):
    return checked(client.post(f"/api/demo/session/{sid}/load-snapshot/{fixture}"))


def feedback(client, sid, step, *, note="用户在演示中模拟完成手动步骤", outcome="unknown"):
    return checked(client.patch(f'/api/session/remediation-plan/steps/{step["step_id"]}',
        json={"session_id": sid, "action": "complete", "outcome": outcome, "user_note": note}))


def run_scenario(client, scenario_id, *, emit=lambda message: None):
    from .scenarios import SCENARIOS
    scenario = SCENARIOS[scenario_id]
    session = checked(client.post("/api/demo/session", json={"scenario_id": scenario_id}))
    sid = session["session_id"]
    assert session["is_demo"] and session["environment_profile"]["client_mode"] == "remote_browser"
    assert session["environment_profile"]["network_access"] == "campus_wifi"
    assert session["diagnostic_target"]["subject"] == "user_client"
    assert session["diagnostic_target"]["relationship_to_netpilot"] == "remote"
    emit("Environment remote browser; Target user_client")
    first = chat(client, sid, scenario.recommended_input)
    assert first["metrics"]["network_tool_calls"] == 0
    assert not first["client_evidence"]
    emit("Host tools blocked before client evidence")
    before = load(client, sid, scenario.snapshot_fixtures[0])
    assert before["client_evidence"] and all(e["evidence_origin"] == "client_snapshot" for e in before["client_evidence"])
    emit("Before snapshot ingested")
    diagnosis = chat(client, sid, "请根据当前快照分析网页问题并给出低风险修复计划。")
    assert diagnosis["diagnosis"]["primary_issue"] == scenario.expected_initial_issue, diagnosis["diagnosis"]
    plan = checked(client.post("/api/session/remediation-plan", json={"session_id": sid}))["remediation_plan"]
    assert plan and plan["steps"] and all(s["risk"] == "low" and not s["requires_admin"] for s in plan["steps"])
    assert set(scenario.expected_remediation_templates).issubset({s["template_id"] for s in plan["steps"]})
    emit("Evidence analyzed; low-risk plan generated")
    if scenario_id in {"dns_recovery", "recurrence"}:
        step = next(s for s in plan["steps"] if s["template_id"] == "campus_reconnect")
        feedback(client, sid, step)
        after = load(client, sid, scenario.snapshot_fixtures[1])
        assert after["verification_cycles"][-1]["result"] == "improved", after["verification_cycles"][-1]
        emit("After snapshot ingested; Verification improved")
        confirmed = checked(client.post("/api/session/resolution/confirm", json={"session_id": sid, "status": "resolved"}))
        assert confirmed["resolution"]["state"] == "resolved", confirmed
        emit("Resolution resolved by objective evidence and user confirmation")
        chat(client, sid, "网页现在可以正常打开了")
        if scenario_id == "recurrence":
            previous = checked(client.get(f"/api/demo/session/{sid}"))["task_version"]
            recurring = chat(client, sid, "刚才好了，现在又打不开了")
            assert recurring["resolution"]["state"] == "diagnosing" and recurring["resolution"]["reason_code"] == "symptom_recurred"
            assert recurring["resolution"]["task_version"] == previous + 1
            assert any(t["to_state"] == "resolved" for t in recurring["resolution_transitions"])
            assert checked(client.get(f"/api/demo/session/{sid}"))["latest_verification_historical"]
            emit("Recurrence reopened next task version; old transition preserved")
    elif scenario_id == "dns_escalation":
        first_step = next(s for s in plan["steps"] if s["template_id"] == "reopen_browser")
        note = "token=demo-note-secret hostname=DESKTOP-DEMO MAC=00-11-22-33-44-55 SSID=DEMO-WLAN https://example.com/?token=demo-query-secret&lang=zh"
        feedback(client, sid, first_step, note=note)
        one = load(client, sid, scenario.snapshot_fixtures[1])
        assert one["verification_cycles"][-1]["result"] == "unchanged"
        emit("Verification V1 unchanged")
        # All remaining approved steps are acknowledged through real feedback,
        # within V2; no step list or Resolution is patched by this runner.
        for step in plan["steps"]:
            if step["step_id"] != first_step["step_id"]: feedback(client, sid, step)
        two = load(client, sid, scenario.snapshot_fixtures[2])
        assert [c["result"] for c in two["verification_cycles"][-2:]] == ["unchanged", "unchanged"]
        assert two["resolution"]["state"] == "escalated" and two["resolution"]["reason_code"] == "repeated_no_improvement", two["resolution"]
        packages = checked(client.post("/api/session/escalation-package", json={"session_id": sid}))
        package = packages["packages"][-1]
        assert package["completeness"] == "complete", package["completeness_notes"]
        completed = [c for c in package["verification_summary"] if c["status"] == "completed"]
        assert len(completed) == 2 and package["recommended_handoff_checks"], [(c["status"], c["result"]) for c in package["verification_summary"]]
        for format in ["md", "json"]:
            exported = client.get(f'/api/session/escalation-package/{package["package_id"]}/export', params={"session_id": sid, "format": format})
            assert exported.status_code == 200, exported.text
            assert "DEMO / 模拟数据" in exported.text, (format, package["is_demo"], exported.text[:100])
            assert all(secret not in exported.text for secret in ["demo-note-secret", "DESKTOP-DEMO", "00-11-22-33-44-55", "DEMO-WLAN", "demo-query-secret"])
        emit("Verification V2 unchanged; escalated; complete privacy-safe package")
    elif scenario_id == "vpn_proxy":
        vpn = next(s for s in plan["steps"] if s["template_id"] == "disconnect_vpn")
        assert vpn["rollback_instructions"] and "不依赖" in vpn["title"]
        assert all(s["status"] == "pending" for s in plan["steps"])
        emit("Conditional VPN disconnect with rollback; no automatic execution")
    elif scenario_id == "vpn_unknown":
        assert all(s["template_id"] != "disconnect_vpn" for s in plan["steps"])
        emit("Unknown VPN requires confirmation, never automatic disconnect")
    elif scenario_id == "single_service":
        assert "single_service" == plan["primary_issue"]
        assert not {"reconnect_network", "campus_reconnect", "disconnect_vpn"}.intersection(s["template_id"] for s in plan["steps"])
        emit("Single-service scope; no global network reset or static DNS change")
    status = checked(client.get(f"/api/demo/session/{sid}"))
    assert status["host_handler_calls"] == 0
    history = checked(client.get("/api/diagnoses", params={"session_id": sid}))["items"]
    assert len(history) == 1 and history[0]["is_demo"]
    record_id = history[0]["record_id"]
    restored = checked(client.get(f"/api/diagnoses/{record_id}"))
    assert restored["conversation_turns"] and restored["is_demo"]
    for format in ["markdown", "json"]:
        report = client.get(f"/api/diagnoses/{record_id}/export", params={"format": format})
        assert report.status_code == 200 and "DEMO / 模拟数据" in report.text
    emit("History restored; report exports labeled DEMO")
    return {"session_id": sid, "record_id": record_id, "status": status, "record": restored, "plan": plan}
