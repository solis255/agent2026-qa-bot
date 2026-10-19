"""Synthetic handoff scenarios only; never real host checks or ticket calls."""
from datetime import datetime, timezone
from resolution_helpers import finished, exhaust, evaluate
from client_snapshot_helpers import payload,import_snapshot


def case():
    _,store,sid,owner,_,_,_=finished("dns_failure")
    task,_=store.verification(sid,owner,action="create",reverify=True)
    store.verification(sid,owner,action="start",cycle_id=task.verification_cycles[-1].verification_id)
    task,_,_=import_snapshot(store,sid,owner,payload("dns_failure"))
    task.environment_profile.network_access="campus_wifi"
    task.environment_profile.proxy_enabled=False
    task.remediation_symptom="连上校园 Wi-Fi，但多个网页打不开"
    task.original_symptom=task.remediation_symptom
    task.issue_started_at=datetime.now(timezone.utc)
    task=exhaust(task)
    task.resolution=evaluate(task)
    assert task.resolution.state == "escalated"
    return task
