"""Metric-aware exact-target comparisons; changed values alone prove no recovery."""
from netpilot.verification.baseline import metric_value
from netpilot.verification.models import EvidenceDiff


def compare(checks, records, *, stale=False):
    observations = {}
    for record in records:
        value = metric_value(record)
        if value: observations[value[:2]] = (record,value[2])
    diffs = []
    for check in checks:
        found = observations.get((check.metric, check.target))
        check.change = "not_comparable"
        check.after_value = found[1] if found else None
        check.after_status = found[0].status if found and found[0].status in {"normal","abnormal","unsupported","error","unknown"} else None
        reason = "缺少同一指标、同一目标的修复后证据。"
        if stale:
            reason = "基线或修复后证据过期或疑似时钟偏差，不能证明当前改善。"
        elif found and check.baseline_status in {"normal","abnormal"} and check.after_status in {"normal","abnormal"}:
            check.change = "improved" if (check.baseline_status,check.after_status) == ("abnormal","normal") else "worsened" if (check.baseline_status,check.after_status) == ("normal","abnormal") else "unchanged"
            reason = {"improved":"同一目标的检测指标改善，不代表全部症状解决。", "worsened":"同一目标的检测指标变差。", "unchanged":"同一目标的检测状态无变化。"}[check.change]
            if check.metric == "network_configuration":
                # Configuration changes cannot imply DNS resolution recovery.
                check.change = "unchanged" if check.baseline_value == check.after_value else "unknown"
                reason = f"配置对比：{check.baseline_value} → {check.after_value}；配置存在不等于 DNS 解析或访问正常。"
        elif found:
            reason = "unsupported / error / unknown 不是正常或改善证据。"
        check.interpretation = reason
        diffs.append(EvidenceDiff(metric=check.metric,target=check.target,before=check.baseline_value,after=check.after_value,change=check.change,interpretation=reason))
    return diffs
