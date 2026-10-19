"""Only select metrics observed in the baseline, never a full diagnostic chain."""
from netpilot.remediation.catalog import CATALOG

ALL_METRICS = ("dns_resolution", "gateway_reachability", "tcp_connectivity", "http_reachability", "network_configuration", "campus_auth", "vpn_state", "proxy_state", "user_observed_symptom")
ISSUE_METRICS = {
    "dns_resolution_failure": {"dns_resolution"}, "local_network_configuration": {"gateway_reachability", "network_configuration"},
    "icmp_unreachable": {"gateway_reachability"}, "tcp_connectivity_failure": {"tcp_connectivity"},
    "http_connectivity_failure": {"http_reachability"}, "proxy_fake_ip_mapping": {"dns_resolution"},
}


class VerificationPlanner:
    def metrics(self, plan):
        metrics = set(ISSUE_METRICS.get(plan.primary_issue, ()))
        for step in plan.steps:
            template = CATALOG.get(step.template_id)
            if template:
                metrics.update(template.verification_metrics)
        return metrics | {"user_observed_symptom"}

    def critical(self, plan, metric):
        return metric in ISSUE_METRICS.get(plan.primary_issue, ())
