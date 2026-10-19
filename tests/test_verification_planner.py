from verification_helpers import remote_cycle,host_cycle
from netpilot.verification.planner import VerificationPlanner
from netpilot.remediation.catalog import CATALOG
from netpilot.verification.baseline import metric_value


def test_metrics_from_issue_and_static_template():
    *_,task=remote_cycle();planner=VerificationPlanner()
    assert "dns_resolution" in planner.metrics(task.remediation_plan)
    assert planner.critical(task.remediation_plan,"dns_resolution")
    assert not planner.critical(task.remediation_plan,"network_configuration")
    assert all(t.verification_metrics for t in CATALOG.values())


def test_only_observed_checks_no_invented_probes():
    *_,task=host_cycle();cycle=task.verification_cycles[-1]
    assert [(c.metric,c.target) for c in cycle.checks] == [("dns_resolution","github.com")]


def test_non_gateway_ping_not_mislabeled_for_dns_plan():
    from netpilot.verification.baseline import freeze
    *_,task=remote_cycle()
    task.evidence.append(task.evidence[0].model_copy(update={"evidence_id":"not-gateway","tool_name":"ping_host","arguments":{"host":"1.1.1.1"},"execution_scope":"client_snapshot","data":{}}))
    baseline,_=freeze(task,task.remediation_plan)
    assert "not-gateway" not in baseline.evidence_ids
