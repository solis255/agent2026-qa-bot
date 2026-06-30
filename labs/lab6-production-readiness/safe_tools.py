#!/usr/bin/env python3
"""
Lab 6: Safety wrappers for production-minded network agents.

This file demonstrates the guardrail layer that should sit between an AI agent
and network infrastructure.

It uses the lab mock devices, but the same pattern applies when the backend
is SSH, NetBox, a controller API, or another network system.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.mock_network_devices import (  # noqa: E402
    MockNetworkDevice,
    execute_command,
    get_bgp_summary,
    get_device_status,
)

READ_ONLY_PREFIXES = ("show",)
DEFAULT_ALLOWED_DEVICES = tuple(MockNetworkDevice.list_devices())
DEFAULT_ALLOWED_SHOW_COMMANDS = (
    "show version",
    "show ip interface brief",
    "show ip bgp summary",
)


@dataclass
class ToolDecision:
    """Result of a safety decision before a backend call runs."""

    allowed: bool
    reason: str
    risk: str = "low"
    requires_approval: bool = False


@dataclass
class AuditEvent:
    """Small structured audit event for every tool request."""

    timestamp: str
    tool: str
    device: Optional[str]
    command: Optional[str]
    decision: ToolDecision
    result_summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = asdict(self.decision)
        return payload


class SafetyPolicy:
    """Policy layer for network agent tools."""

    def __init__(
        self,
        allowed_devices: Iterable[str] = DEFAULT_ALLOWED_DEVICES,
        allowed_show_commands: Iterable[str] = DEFAULT_ALLOWED_SHOW_COMMANDS,
    ) -> None:
        self.allowed_devices = {device.lower() for device in allowed_devices}
        self.allowed_show_commands = {command.lower() for command in allowed_show_commands}

    def evaluate_device(self, device: str) -> ToolDecision:
        if not device:
            return ToolDecision(False, "device is required")

        if device.lower() not in self.allowed_devices:
            return ToolDecision(
                False,
                f"device '{device}' is not in the approved device allowlist",
            )

        return ToolDecision(True, "device approved")

    def evaluate_command(self, device: str, command: str) -> ToolDecision:
        device_decision = self.evaluate_device(device)
        if not device_decision.allowed:
            return device_decision

        clean_command = command.strip().lower()
        if not clean_command.startswith(READ_ONLY_PREFIXES):
            return ToolDecision(
                False,
                "configuration and exec commands are blocked; only read-only show commands are allowed",
                risk="high",
                requires_approval=True,
            )

        if clean_command not in self.allowed_show_commands:
            return ToolDecision(
                False,
                "show command is read-only but not in the approved command allowlist",
                risk="medium",
                requires_approval=True,
            )

        return ToolDecision(True, "read-only command approved")


class AuditLogger:
    """In-memory audit logger used by the lab.

    In production, write these events to a durable destination such as a log
    pipeline, SIEM, database, or case record.
    """

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(
        self,
        tool: str,
        decision: ToolDecision,
        result_summary: str,
        device: Optional[str] = None,
        command: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool=tool,
            device=device,
            command=command,
            decision=decision,
            result_summary=result_summary,
            metadata=metadata or {},
        )
        self.events.append(event)

    def print_events(self) -> None:
        for event in self.events:
            print(json.dumps(event.to_dict(), indent=2))


class SafeNetworkTools:
    """Guarded network tool facade used by an AI agent."""

    def __init__(self, policy: Optional[SafetyPolicy] = None, audit: Optional[AuditLogger] = None) -> None:
        self.policy = policy or SafetyPolicy()
        self.audit = audit or AuditLogger()

    def device_status(self, device: str) -> Dict[str, Any]:
        decision = self.policy.evaluate_device(device)
        if not decision.allowed:
            result = {"error": decision.reason, "allowed": False}
            self.audit.record("device_status", decision, "blocked", device=device)
            return result

        result = get_device_status(device)
        self.audit.record("device_status", decision, "success", device=device)
        return result

    def bgp_summary(self, device: str) -> Dict[str, Any]:
        decision = self.policy.evaluate_device(device)
        if not decision.allowed:
            result = {"error": decision.reason, "allowed": False}
            self.audit.record("bgp_summary", decision, "blocked", device=device)
            return result

        result = get_bgp_summary(device)
        self.audit.record("bgp_summary", decision, "success", device=device)
        return result

    def show_command(self, device: str, command: str) -> Dict[str, Any]:
        decision = self.policy.evaluate_command(device, command)
        if not decision.allowed:
            result = {
                "error": decision.reason,
                "allowed": False,
                "risk": decision.risk,
                "requires_approval": decision.requires_approval,
            }
            self.audit.record("show_command", decision, "blocked", device=device, command=command)
            return result

        output = execute_command(device, command)
        result = {
            "device": device,
            "command": command,
            "output": output,
            "allowed": True,
            "mode": "read_only_mock",
        }
        self.audit.record("show_command", decision, "success", device=device, command=command)
        return result


def demo() -> None:
    tools = SafeNetworkTools()

    print("\n✅ Allowed device status")
    print(json.dumps(tools.device_status("spine1"), indent=2))

    print("\n✅ Allowed BGP summary")
    print(json.dumps(tools.bgp_summary("leaf2"), indent=2))

    print("\n✅ Allowed show command")
    print(json.dumps(tools.show_command("spine1", "show ip bgp summary"), indent=2))

    print("\n🚫 Blocked unsafe command")
    print(json.dumps(tools.show_command("spine1", "configure terminal"), indent=2))

    print("\n🚫 Blocked unknown device")
    print(json.dumps(tools.device_status("core99"), indent=2))

    print("\n📋 Audit events")
    tools.audit.print_events()


if __name__ == "__main__":
    demo()
