"""Fail-closed capabilities calculated from subject, provider and Tool metadata."""

from pydantic import BaseModel
from netpilot.diagnostic_target import DiagnosticTarget, target_limitation


class TargetCapability(BaseModel):
    can_use_host_network_tools: bool = False
    can_use_mock_tools: bool = False
    can_use_target_neutral_tools: bool = True
    can_use_client_snapshot_evidence: bool = False
    reason: str

    def allows_scope(self, scope: str | None) -> bool:
        return {
            "execution_host":self.can_use_host_network_tools,
            "mock_target":self.can_use_mock_tools,
            "target_neutral":self.can_use_target_neutral_tools,
        }.get(scope, False)


def evaluate_target_capabilities(target: DiagnosticTarget, provider_kind: str, *, has_client_snapshot_evidence: bool = False) -> TargetCapability:
    # Recompute rather than trusting a stored limitation code or applicability flag.
    reason = target_limitation(target.subject, target.relationship_to_netpilot, provider_kind)
    return TargetCapability(
        can_use_host_network_tools=(provider_kind == "local" and target.execution_context == "netpilot_host" and reason == "none"),
        can_use_mock_tools=(provider_kind == "mock" and target.execution_context == "mock_provider" and reason == "none"),
        can_use_client_snapshot_evidence=(has_client_snapshot_evidence and target.subject == "user_client" and target.relationship_to_netpilot == "remote"),
        reason=reason,
    )
