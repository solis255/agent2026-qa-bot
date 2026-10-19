"""Freeze normalized metric summaries and references, never duplicate raw evidence."""
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from netpilot.remediation.planner import scoped_evidence
from netpilot.verification.models import VerificationCheck, VerificationEvidenceSet
from netpilot.verification.planner import VerificationPlanner

LABELS = {"normal":"正常", "abnormal":"异常", "unknown":"未知", "unsupported":"不支持", "error":"采集错误"}


def normalized_host(value):
    from netpilot.tools.validation import normalize_host
    try: return normalize_host(str(value or "").strip())
    except ValueError: return ""


def metric_value(record):
    """Identity comes from typed probe args, not status/answer text."""
    name, data, args = record.tool_name, record.data, record.arguments
    if name in {"dns_lookup", "client_snapshot.dns_check"}:
        return "dns_resolution", normalized_host(args.get("domain", data.get("target"))), LABELS.get(record.status, "未知")
    if name in {"tcp_check", "client_snapshot.tcp_connectivity"}:
        host = normalized_host(args.get("host", data.get("target")))
        port = args.get("port", data.get("port"))
        return "tcp_connectivity", f"{host}:{port}", LABELS.get(record.status, "未知")
    if name in {"ping_host", "client_snapshot.gateway_reachability"}:
        # Ordinary ICMP hosts must not masquerade as the default gateway.
        return "gateway_reachability", normalized_host(args.get("host", data.get("target"))), LABELS.get(record.status, "未知")
    if name == "http_check":
        try:
            url = urlsplit(args.get("url", ""))
            host = normalized_host(url.hostname)
            if ":" in host: host = f"[{host}]"
            port = url.port
            authority = host if port is None or (url.scheme.lower(), port) in {("http",80),("https",443)} else f"{host}:{port}"
            target = urlunsplit((url.scheme.lower(), authority, url.path or "/", url.query, ""))
        except ValueError:
            return None
        return "http_reachability", target, LABELS.get(record.status, "未知")
    if name in {"get_network_info", "client_snapshot.network_config"}:
        servers = data.get("dns_servers")
        dns = "存在" if servers else "缺失" if name == "get_network_info" or data.get("collection_status", {}).get("dns_servers") == "normal" else "未知"
        ipv4 = bool(data.get("ipv4")) if name == "get_network_info" else data.get("ipv4_configured")
        return "network_configuration", "active_network", f"DNS 配置：{dns}；IPv4：{'存在' if ipv4 is True else '缺失' if ipv4 is False else '未知'}；默认网关：{'存在' if data.get('default_gateway') else '未知'}"
    return None


def eligible(task):
    return [r for r in scoped_evidence(task.evidence, task.diagnostic_target, task.task_version)
            if r.evidence_origin in {"tool","client_snapshot"}
            and (r.execution_scope != "execution_host" or r.execution_context == "netpilot_host")]


def evidence_set(records, task_version, *, captured_at=None):
    snapshot_ids = {r.snapshot_id for r in records if r.snapshot_id}
    snapshot = records[0] if records and len(snapshot_ids) == 1 and all(r.evidence_origin == "client_snapshot" for r in records) else None
    now = datetime.now(timezone.utc)
    return VerificationEvidenceSet(captured_at=captured_at or now, evidence_ids=tuple(r.evidence_id for r in records),
        snapshot_id=snapshot.snapshot_id if snapshot else None, snapshot_sequence=snapshot.snapshot_sequence if snapshot else None,
        source_kind="client_snapshot" if snapshot else "mock_tools" if records and all(r.execution_scope == "mock_target" for r in records) else "host_tools" if records else "user_observation",
        stale=any(r.stale or r.clock_skew_suspected or (r.expires_at and now > r.expires_at) for r in records), task_version=task_version)


def freeze(task, plan):
    records = eligible(task)
    planner = VerificationPlanner()
    allowed = planner.metrics(plan)
    # For gateway metric, only accept the actual gateway, unless primary issue is ICMP.
    gateways = {normalized_host(r.data.get("default_gateway")) for r in records if r.tool_name in {"get_network_info", "client_snapshot.network_config"} and r.data.get("default_gateway")}
    selected, checks, seen = [], [], set()
    for record in reversed(records):
        if len(checks) >= 100: break
        item = metric_value(record)
        if item is None: continue
        metric, target, value = item
        if metric not in allowed or (metric,target) in seen: continue
        if record.tool_name == "ping_host" and target not in gateways and plan.primary_issue != "icmp_unreachable": continue
        seen.add((metric,target)); selected.append(record)
        checks.append(VerificationCheck(metric=metric,target=target,baseline_value=value,baseline_status=record.status if record.status in LABELS else "unknown",
            importance="critical" if planner.critical(plan,metric) else "supporting"))
    selected.reverse(); checks.reverse()
    return evidence_set(selected, task.task_version), checks
