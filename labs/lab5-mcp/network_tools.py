#!/usr/bin/env python3
"""
Safe network tool wrappers for Lab 5.

These wrappers keep the MCP layer thin. The real network logic stays in the
existing lab mock device module so Lab 5 builds on Lab 4 instead of
creating a second topology model.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Allow this lab to import from the repository-level examples folder when run
# directly with: python3 labs/lab5-mcp/client_test.py
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.mock_network_devices import (  # noqa: E402
    MockNetworkDevice,
    execute_command,
    get_bgp_summary,
    get_device_status,
    get_interface_status,
    get_topology_info,
    ping_device,
)

ALLOWED_SHOW_PREFIX = "show"


def list_devices() -> Dict[str, Any]:
    """Return the devices available in the lab topology."""
    return {
        "source": "mock_network_devices",
        "devices": MockNetworkDevice.list_devices(),
    }


def validate_device(device: str) -> Optional[Dict[str, Any]]:
    """Return an error payload if the device is unknown."""
    if not device:
        return {"error": "device is required", "available_devices": MockNetworkDevice.list_devices()}

    if not MockNetworkDevice.device_exists(device):
        return {
            "error": f"Device '{device}' is not in the lab topology",
            "available_devices": MockNetworkDevice.list_devices(),
        }

    return None


def safe_device_status(device: str) -> Dict[str, Any]:
    """Return operational status for one lab device."""
    error = validate_device(device)
    if error:
        return error
    return get_device_status(device)


def safe_interface_status(device: str, interface: Optional[str] = None) -> Dict[str, Any]:
    """Return all interfaces or one interface for a lab device."""
    error = validate_device(device)
    if error:
        return error
    return get_interface_status(device, interface=interface)


def safe_bgp_summary(device: str) -> Dict[str, Any]:
    """Return BGP summary information for a lab device."""
    error = validate_device(device)
    if error:
        return error
    return get_bgp_summary(device)


def safe_ping(target: str, count: int = 4) -> Dict[str, Any]:
    """Run a mock reachability check against a lab target."""
    if count < 1 or count > 10:
        return {"error": "count must be between 1 and 10"}
    return ping_device(target, count)


def safe_show_command(device: str, command: str) -> Dict[str, Any]:
    """Execute a read-only show command against a lab device."""
    error = validate_device(device)
    if error:
        return error

    clean_command = command.strip()
    if not clean_command.lower().startswith(ALLOWED_SHOW_PREFIX):
        return {
            "error": "Only read-only show commands are allowed in this lab",
            "blocked_command": command,
            "example": "show ip bgp summary",
        }

    output = execute_command(device, clean_command)
    return {
        "device": device,
        "command": clean_command,
        "output": output,
        "mode": "read_only_mock",
    }


def safe_topology_info() -> Dict[str, Any]:
    """Return the lab topology map."""
    return get_topology_info()
