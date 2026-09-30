"""Lightweight, deterministic hypothesis tracking over structured evidence."""

from __future__ import annotations

import ipaddress
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from netpilot.agent.coverage import Observation, normalize_observations


HypothesisStatus = Literal["possible", "supported", "weakened", "excluded"]


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    status: HypothesisStatus
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


def track_hypotheses(
    *,
    steps: Sequence[Any] = (),
    evidence: Sequence[Any] = (),
) -> list[Hypothesis]:
    observations = normalize_observations(steps=steps, evidence=evidence)
    if not observations:
        return []
    hypotheses: list[Hypothesis] = []
    dns_abnormal = _matching(observations, "dns_lookup", "abnormal")
    ping_normal = _matching(observations, "ping_host", "normal")
    ping_abnormal = _matching(observations, "ping_host", "abnormal")
    network_normal = _matching(observations, "get_network_info", "normal")
    network_abnormal = _matching(observations, "get_network_info", "abnormal")

    if dns_abnormal:
        dns_ids = _ids(dns_abnormal)
        hypotheses.append(
            Hypothesis(
                name="dns_resolution_path_failure",
                status="supported",
                supporting_evidence_ids=dns_ids,
            )
        )
        hypotheses.append(
            Hypothesis(
                name="local_dns_configuration_issue",
                status=(
                    "supported"
                    if network_abnormal
                    else "weakened"
                    if network_normal
                    else "possible"
                ),
                supporting_evidence_ids=_ids(network_abnormal),
                contradicting_evidence_ids=_ids(network_normal),
                missing_evidence=(
                    [] if network_abnormal else ["compare configured DNS with a known resolver"]
                ),
            )
        )
        hypotheses.append(
            Hypothesis(
                name="proxy_dns_interception",
                status="supported" if _has_fake_ip(observations) else "possible",
                supporting_evidence_ids=(dns_ids if _has_fake_ip(observations) else []),
                missing_evidence=([] if _has_fake_ip(observations) else ["VPN/Proxy state"]),
            )
        )
        distinct_domains = {
            str(item.arguments.get("domain", "")).casefold()
            for item in dns_abnormal
            if item.arguments.get("domain")
        }
        hypotheses.append(
            Hypothesis(
                name="single_site_failure",
                status="weakened" if len(distinct_domains) >= 2 else "possible",
                contradicting_evidence_ids=(dns_ids if len(distinct_domains) >= 2 else []),
                missing_evidence=([] if len(distinct_domains) >= 2 else ["second unrelated domain"]),
            )
        )

    if ping_normal or ping_abnormal or dns_abnormal:
        hypotheses.append(
            Hypothesis(
                name="overall_ip_connectivity_failure",
                status=(
                    "excluded" if ping_normal else "supported" if ping_abnormal else "possible"
                ),
                supporting_evidence_ids=_ids(ping_abnormal),
                contradicting_evidence_ids=_ids(ping_normal),
                missing_evidence=([] if ping_normal or ping_abnormal else ["public IP reachability"]),
            )
        )
    return hypotheses


def _matching(
    observations: list[Observation],
    tool_name: str,
    status: str,
) -> list[Observation]:
    return [
        item
        for item in observations
        if item.tool_name == tool_name and item.status == status
    ]


def _ids(observations: list[Observation]) -> list[str]:
    return [item.evidence_id for item in observations]


def _has_fake_ip(observations: list[Observation]) -> bool:
    network = ipaddress.ip_network("198.18.0.0/15")
    for item in observations:
        for key in ("addresses", "resolved_addresses"):
            for value in item.data.get(key, []):
                try:
                    if ipaddress.ip_address(value) in network:
                        return True
                except ValueError:
                    continue
    return False
