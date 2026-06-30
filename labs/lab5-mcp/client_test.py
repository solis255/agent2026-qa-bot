#!/usr/bin/env python3
"""
Local sanity test for Lab 5 network tools.

This does not start an MCP client. It validates the business logic that the MCP
server exposes, which makes troubleshooting much easier.
"""

from __future__ import annotations

import json

from network_tools import (
    list_devices,
    safe_bgp_summary,
    safe_device_status,
    safe_interface_status,
    safe_ping,
    safe_show_command,
    safe_topology_info,
)


def pretty(title: str, payload: dict) -> None:
    print(f"\n{'=' * 70}")
    print(title)
    print("=" * 70)
    print(json.dumps(payload, indent=2))


def main() -> None:
    pretty("Available devices", list_devices())
    pretty("Device status: spine1", safe_device_status("spine1"))
    pretty("BGP summary: leaf2", safe_bgp_summary("leaf2"))
    pretty("Interface status: leaf2 all interfaces", safe_interface_status("leaf2"))
    pretty("Interface status: leaf2 Ethernet3", safe_interface_status("leaf2", "Ethernet3"))
    pretty("Ping: leaf1", safe_ping("leaf1"))
    pretty("Topology", safe_topology_info())
    pretty("Allowed show command", safe_show_command("spine1", "show ip bgp summary"))
    pretty("Blocked unsafe command", safe_show_command("spine1", "configure terminal"))


if __name__ == "__main__":
    main()
