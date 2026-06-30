#!/usr/bin/env python3
"""
Lab 5: MCP server for the book lab network tools.

Run from the repository root:
    python3 labs/lab5-mcp/mcp_server.py

This server exposes the lab mock network functions through MCP so the
same tools can be reused by MCP-capable clients.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from network_tools import (
    list_devices,
    safe_bgp_summary,
    safe_device_status,
    safe_interface_status,
    safe_ping,
    safe_show_command,
    safe_topology_info,
)

mcp = FastMCP("ai-networking-workshop")


@mcp.tool()
def devices() -> dict:
    """List the devices available in the lab mock network."""
    return list_devices()


@mcp.tool()
def device_status(device: str) -> dict:
    """Get read-only operational status for a network device.

    Args:
        device: Device hostname, such as spine1, spine2, leaf1, or leaf2.
    """
    return safe_device_status(device)


@mcp.tool()
def interface_status(device: str, interface: Optional[str] = None) -> dict:
    """Get interface state for a device.

    Args:
        device: Device hostname.
        interface: Optional interface name, such as Ethernet1. Leave empty to
            return all interfaces on the device.
    """
    return safe_interface_status(device, interface)


@mcp.tool()
def bgp_summary(device: str) -> dict:
    """Get BGP neighbor summary for a workshop network device.

    Args:
        device: Device hostname, such as spine1, spine2, leaf1, or leaf2.
    """
    return safe_bgp_summary(device)


@mcp.tool()
def ping(target: str, count: int = 4) -> dict:
    """Run a mock reachability check against a target.

    Args:
        target: Device hostname or IP address.
        count: Number of packets to simulate. Must be between 1 and 10.
    """
    return safe_ping(target, count)


@mcp.tool()
def show_command(device: str, command: str) -> dict:
    """Execute a read-only show command against a workshop device.

    This lab blocks configuration commands. Use commands such as:
    - show version
    - show ip interface brief
    - show ip bgp summary

    Args:
        device: Device hostname.
        command: Read-only command that starts with show.
    """
    return safe_show_command(device, command)


@mcp.tool()
def topology() -> dict:
    """Return the workshop spine-leaf topology."""
    return safe_topology_info()


if __name__ == "__main__":
    import sys
    # Run with --sse for the UI bridge (HTTP/SSE transport on port 8000)
    # Run without flags for stdio mode (Claude Desktop, MCP CLI, etc.)
    transport = "sse" if "--sse" in sys.argv else "stdio"
    print(f"Starting MCP server in {transport} mode...")
    if transport == "sse":
        print("  Listening on http://localhost:8000")
        print("  Start the bridge next: python3 labs/lab5-mcp/http_bridge.py")
    mcp.run(transport=transport)
