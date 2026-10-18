from datetime import datetime, timedelta, timezone
import pytest
from client_snapshot_helpers import payload, import_snapshot
from target_helpers import local_session, run
from netpilot.agent.coverage import coverage_from_observations
from netpilot.client_snapshot.service import snapshot_context


def test_cs03_multi_dns_aggregated_real_evidence_names_no_tool_calls():
    agent, store, sid, owner, counts, llm = local_session()
    task, _, _ = import_snapshot(store, sid, owner, payload("dns_failure"))
    assert {item.evidence_origin for item in task.evidence} == {"client_snapshot"}
    assert all(item.tool_name.startswith("client_snapshot.") for item in task.evidence)
    assert all(item.observed_at == task.client_snapshot_summary.generated_at for item in task.evidence)
    result = run(agent, store, sid, owner, "网页打不开，完整诊断我的电脑网络")
    assert result.answer.count("DNS 解析失败：") == 1
    assert "www.tju.edu.cn、www.baidu.com" in result.answer
    assert "唯一根因" in result.answer
    assert len(result.reused_evidence_ids) == 5
    assert not result.steps and sum(counts.values()) == 0 and not llm.calls
    assert result.coverage.dns_checked and result.coverage.tcp_checked
    assert not result.coverage.ip_connectivity_checked  # gateway != public IP connectivity
    assert next(item for item in result.hypotheses if item.name == "single_site_failure").status == "weakened"


@pytest.mark.parametrize("status", ["unsupported", "error"])
def test_cs05_unknown_is_not_abnormal(status):
    agent, store, sid, owner, counts, _ = local_session()
    value = payload()
    value["checks"][0].update(status=status,result={"error_code":"cmdlet_unavailable" if status == "unsupported" else "collection_error"})
    value["checks"][1].update(status=status,result={"error_code":"collection_error"})
    task, _, _ = import_snapshot(store, sid, owner, value)
    assert not task.coverage.dns_checked
    assert not any(item.name == "dns_resolution_path_failure" for item in task.hypotheses)
    answer = run(agent, store, sid, owner, "根据快照分析网络").answer
    assert "状态未知" in answer and "DNS 解析失败：" not in answer


@pytest.mark.parametrize("minutes,stale,skew", [(-16,True,False),(10,False,True)])
def test_cs06_cs07_stale_and_future_never_current(minutes, stale, skew):
    agent, store, sid, owner, counts, _ = local_session()
    value = payload("dns_failure")
    value["generated_at"] = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    task, _, events = import_snapshot(store, sid, owner, value)
    summary = task.client_snapshot_summary
    assert summary.stale is stale and summary.clock_skew_suspected is skew
    assert not task.coverage.dns_checked and not task.hypotheses
    assert any(item.title == "快照时效限制" for item in events)
    result = run(agent, store, sid, owner, "根据已有证据分析网络")
    assert "历史" in result.answer if stale else "时钟" in result.answer
    assert sum(counts.values()) == 0


def test_freshness_recomputed_without_reupload():
    agent, store, sid, owner, _, _ = local_session()
    task, _, _ = import_snapshot(store, sid, owner)
    live = store._sessions[sid].task_state
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    live.client_snapshot_summary.expires_at = past
    for item in live.evidence:
        item.expires_at = past
    refreshed = store.task_state(sid, owner)
    assert refreshed.client_snapshot_summary.stale
    assert not coverage_from_observations(evidence=refreshed.reusable_evidence()).dns_checked
    assert "历史证据" in snapshot_context(refreshed.reusable_evidence())


def test_cs04_gateway_missing_and_failed_have_distinct_meanings():
    agent, store, sid, owner, _, _ = local_session()
    value = payload()
    value["default_gateway"] = None
    value["checks"][2].update(target="unknown",status="error",result={"error_code":"gateway_unknown"})
    task, _, _ = import_snapshot(store, sid, owner, value)
    assert not task.coverage.gateway_checked
    assert next(item for item in task.evidence if item.tool_name.endswith("network_config")).status == "unknown"
    value = payload()
    value["checks"][2].update(status="abnormal",result={"reachable":False})
    task, _, _ = import_snapshot(store, sid, owner, value)
    assert task.coverage.gateway_checked
    assert next(item for item in task.reusable_evidence() if item.tool_name.endswith("gateway_reachability")).status == "abnormal"


def test_missing_ip_collection_is_unknown_not_false():
    _,store,sid,owner,_,_=local_session()
    value=payload()
    value["adapters"][0]["ipv4_addresses"]=[]
    value["collection_status"]={"ip_configuration":"unsupported"}
    task,_,_=import_snapshot(store,sid,owner,value)
    config=next(item for item in task.evidence if item.tool_name.endswith("network_config"))
    assert config.data["ipv4_configured"] is None and config.status == "unknown"


def test_extreme_future_timestamp_is_warning_not_server_exception():
    _,store,sid,owner,_,_=local_session()
    value=payload()
    value["generated_at"]="9999-12-31T23:59:59Z"
    task,_,_=import_snapshot(store,sid,owner,value)
    assert task.client_snapshot_summary.clock_skew_suspected
