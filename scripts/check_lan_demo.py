"""Read-only preflight for the direct-HTTP, trusted-LAN competition demo.

This does not open a listener, contact the model, alter the firewall, or print
credentials. Browser reachability and RAG runtime readiness need manual checks.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from pydantic import ValidationError

from netpilot.config import Settings, ToolMode


_TRUSTED_LAN_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


@dataclass(frozen=True)
class Check:
    label: str
    ready: bool
    action: str


def _lan_bind(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return isinstance(address, ipaddress.IPv4Address) and (
        address == ipaddress.IPv4Address("0.0.0.0")
        or any(address in network for network in _TRUSTED_LAN_NETWORKS)
    )


def assess(settings: Settings) -> list[Check]:
    index_files = ("vectors.faiss", "chunks.json", "manifest.json")
    return [
        Check("Authentication required", settings.auth_enabled is True, "Set AUTH_ENABLED=true."),
        Check("Model key configured", settings.llm_configured, "Set TJU_API_KEY in private .env."),
        Check("Mock Provider", settings.tool_mode is ToolMode.MOCK, "Set TOOL_MODE=mock."),
        Check(
            "Scenario switching", settings.scenario_switch_enabled,
            "Set SCENARIO_SWITCH_ENABLED=true.",
        ),
        Check(
            "Diagnosis history", settings.diagnosis_history_enabled,
            "Set DIAGNOSIS_HISTORY_ENABLED=true.",
        ),
        Check("Trusted LAN bind", _lan_bind(settings.app_host), "Set APP_HOST=0.0.0.0 or a trusted RFC1918 IPv4 address."),
        Check(
            "HTTP cookie compatible", not settings.auth_cookie_secure,
            "For direct HTTP only, set AUTH_COOKIE_SECURE=false. Do not use this preflight for HTTPS.",
        ),
        Check("Debug disabled", not settings.debug, "Set DEBUG=false."),
        Check("RAG enabled", settings.rag_enabled, "Set RAG_ENABLED=true."),
        Check(
            "Local RAG index files",
            all((settings.rag_index_dir / name).is_file() for name in index_files),
            "Run python scripts/build_knowledge_index.py, then verify /api/health has rag_ready=true.",
        ),
    ]


def main() -> int:
    try:
        settings = Settings()
    except ValidationError:
        print("Configuration validation failed. Check private .env or environment variables; values are not echoed.")
        return 2

    checks = assess(settings)
    for check in checks:
        print(f"{'OK' if check.ready else 'ACTION REQUIRED'}  {check.label}")
        if not check.ready:
            print(f"  {check.action}")
    print("\nHTTP login passwords are unencrypted in transit. Use dedicated, non-reused demo accounts only; never school SSO credentials.")
    print("Manually verify firewall scope, reachability from another trusted device, and /api/health rag_ready=true.")
    return 0 if all(check.ready for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
