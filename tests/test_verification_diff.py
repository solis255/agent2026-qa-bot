import pytest
from verification_helpers import remote_cycle
from netpilot.verification.models import VerificationCheck
from netpilot.verification.diff import compare


@pytest.mark.parametrize("before,after,expected",[("abnormal","normal","improved"),("normal","abnormal","worsened"),("normal","normal","unchanged"),("abnormal","abnormal","unchanged"),("error","normal","not_comparable"),("abnormal","unsupported","not_comparable")])
def test_dns_semantics(before,after,expected):
    *_,task=remote_cycle();record=next(e for e in task.evidence if e.tool_name.endswith("dns_check"))
    check=VerificationCheck(metric="dns_resolution",target=record.data["target"],baseline_status=before,baseline_value=before,importance="critical")
    diffs=compare([check],[record.model_copy(update={"status":after})])
    assert diffs[0].change == expected


@pytest.mark.parametrize("metric,target,data",[("dns_resolution","different.example",{"target":"www.baidu.com"}),("tcp_connectivity","github.com:22",{"target":"github.com","port":443})])
def test_bv04_exact_domain_and_tcp_port(metric,target,data):
    *_,task=remote_cycle();record=task.evidence[0].model_copy(update={"tool_name":"client_snapshot.dns_check" if metric == "dns_resolution" else "client_snapshot.tcp_connectivity","data":data,"status":"normal"})
    check=VerificationCheck(metric=metric,target=target,baseline_status="abnormal")
    assert compare([check],[record])[0].change == "not_comparable"


def test_config_change_not_dns_recovery():
    *_,task=remote_cycle();record=task.evidence[0]
    check=VerificationCheck(metric="network_configuration",target="active_network",baseline_status="normal",baseline_value="DNS 配置：缺失")
    diff=compare([check],[record])[0]
    assert diff.change == "unknown" and "不等于 DNS" in diff.interpretation


def test_host_normalization_and_stale_no_recovery():
    *_,task=remote_cycle();record=task.evidence[1].model_copy(update={"data":{"target":"WWW.TJU.EDU.CN."},"status":"normal"})
    check=VerificationCheck(metric="dns_resolution",target="www.tju.edu.cn",baseline_status="abnormal")
    assert compare([check],[record])[0].change == "improved"
    assert compare([check],[record],stale=True)[0].change == "not_comparable"


def test_bv03_gateway_worsened_same_gateway_only():
    *_,task=remote_cycle();record=next(r for r in task.evidence if r.tool_name.endswith("gateway_reachability"))
    check=VerificationCheck(metric="gateway_reachability",target=record.data["target"],baseline_status="normal",importance="critical")
    assert compare([check],[record.model_copy(update={"status":"abnormal"})])[0].change == "worsened"
    assert compare([check],[record.model_copy(update={"data":{"target":"192.168.20.1"},"status":"normal"})])[0].change == "not_comparable"
