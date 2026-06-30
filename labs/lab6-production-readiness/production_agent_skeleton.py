#!/usr/bin/env python3
"""
Lab 6: Mock-to-real backend pattern for production-readiness reviews.

This example keeps the agent-facing tool contract stable while allowing the
backend implementation to change from mock data to real infrastructure later.
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.mock_network_devices import execute_command, get_bgp_summary, get_device_status  # noqa: E402


@dataclass
class ToolResult:
    """Normalized tool result returned to the agent."""

    ok: bool
    source: str
    data: Dict[str, Any]
    error: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "source": self.source,
            "data": self.data,
            "error": self.error,
        }


class NetworkBackend(ABC):
    """Interface every network backend must implement."""

    @abstractmethod
    def device_status(self, device: str) -> ToolResult:
        """Return device status."""

    @abstractmethod
    def bgp_summary(self, device: str) -> ToolResult:
        """Return BGP summary."""

    @abstractmethod
    def show_command(self, device: str, command: str) -> ToolResult:
        """Run a read-only show command."""


class MockNetworkBackend(NetworkBackend):
    """Lab backend using the included mock devices."""

    def device_status(self, device: str) -> ToolResult:
        data = get_device_status(device)
        return ToolResult(ok="error" not in data, source="mock", data=data, error=data.get("error"))

    def bgp_summary(self, device: str) -> ToolResult:
        data = get_bgp_summary(device)
        return ToolResult(ok="error" not in data, source="mock", data=data, error=data.get("error"))

    def show_command(self, device: str, command: str) -> ToolResult:
        output = execute_command(device, command)
        ok = not output.lower().startswith("error:")
        return ToolResult(
            ok=ok,
            source="mock",
            data={"device": device, "command": command, "output": output},
            error=None if ok else output,
        )


class RealNetworkBackend(NetworkBackend):
    """Placeholder for a future real-device backend.

    Swap this implementation with Netmiko, Paramiko, NAPALM, controller APIs,
    NetBox-enriched lookups, or your preferred network access method.

    Keep the method names and return shape the same. That is the whole point of
    the backend pattern: the agent does not need to care whether the source is
    mock data, SSH, or an API.
    """

    def device_status(self, device: str) -> ToolResult:
        return ToolResult(
            ok=False,
            source="real",
            data={"device": device},
            error="RealNetworkBackend.device_status is not implemented yet",
        )

    def bgp_summary(self, device: str) -> ToolResult:
        return ToolResult(
            ok=False,
            source="real",
            data={"device": device},
            error="RealNetworkBackend.bgp_summary is not implemented yet",
        )

    def show_command(self, device: str, command: str) -> ToolResult:
        return ToolResult(
            ok=False,
            source="real",
            data={"device": device, "command": command},
            error="RealNetworkBackend.show_command is not implemented yet",
        )


class ProductionReadyToolFacade:
    """Agent-facing facade with a stable contract."""

    def __init__(self, backend: NetworkBackend) -> None:
        self.backend = backend

    def investigate_bgp(self, device: str) -> Dict[str, Any]:
        """Small example of composing multiple backend calls."""
        status = self.backend.device_status(device)
        bgp = self.backend.bgp_summary(device)

        return {
            "device": device,
            "checks": {
                "device_status": status.to_dict(),
                "bgp_summary": bgp.to_dict(),
            },
            "summary": self._summarize_bgp(status, bgp),
        }

    @staticmethod
    def _summarize_bgp(status: ToolResult, bgp: ToolResult) -> str:
        if not status.ok:
            return f"Device status check failed: {status.error}"
        if not bgp.ok:
            return f"BGP check failed: {bgp.error}"

        total = bgp.data.get("total_peers", 0)
        established = bgp.data.get("established_peers", 0)
        if total == established:
            return f"All {total} BGP peers are established."
        return f"BGP issue detected: {established}/{total} peers are established."


def demo() -> None:
    print("\n=== Mock backend demo ===")
    mock_facade = ProductionReadyToolFacade(MockNetworkBackend())
    print(json.dumps(mock_facade.investigate_bgp("leaf2"), indent=2))

    print("\n=== Real backend placeholder demo ===")
    real_facade = ProductionReadyToolFacade(RealNetworkBackend())
    print(json.dumps(real_facade.investigate_bgp("leaf2"), indent=2))


if __name__ == "__main__":
    demo()
