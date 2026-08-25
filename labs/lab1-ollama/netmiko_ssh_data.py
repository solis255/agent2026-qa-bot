#!/usr/bin/env python3
"""
Lab 1: Netmiko SSH Data Collection + TJU API Analysis
Building AI Agents for Network Operations

LAB MODE:  USE_MOCK = True  (works without any devices)
AFTER THE LAB:  Set USE_MOCK = False and update DEVICE_CONFIG

What this shows:
- SSH into network devices with Netmiko (same pattern as production)
- Collect raw 'show' command output
- Feed real CLI output directly into tju-llm for AI analysis
"""

import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.tju_llm_client import DEFAULT_MODEL, TJUAPIError, generate_text

# ============================================================================
# TOGGLE: Mock data vs live SSH
# ============================================================================

USE_MOCK = True  # Flip to False with real devices after the lab

DEVICE_CONFIG = {
    "spine1": {"device_type": "arista_eos", "host": "192.168.0.11", "username": "admin", "password": "admin", "port": 22},
    "spine2": {"device_type": "arista_eos", "host": "192.168.0.12", "username": "admin", "password": "admin", "port": 22},
    "leaf1":  {"device_type": "arista_eos", "host": "192.168.0.21", "username": "admin", "password": "admin", "port": 22},
    "leaf2":  {"device_type": "arista_eos", "host": "192.168.0.22", "username": "admin", "password": "admin", "port": 22},
}

# ============================================================================
# MOCK DATA — realistic Arista EOS output
# ============================================================================

_MOCK = {
    "show version": {
        "spine1": (
            "Arista cEOS\nSerial number: SPX2134567890\n"
            "Software image version: 4.28.0F\nUptime: 5 days, 3 hours\n"
            "Total memory: 4096 MB  Free memory: 2048 MB"
        ),
        "spine2": (
            "Arista cEOS\nSerial number: SPX2134567891\n"
            "Software image version: 4.28.0F\nUptime: 7 days, 1 hour\n"
            "Total memory: 4096 MB  Free memory: 2100 MB"
        ),
        "leaf1": (
            "Arista cEOS\nSerial number: LFX2134567890\n"
            "Software image version: 4.27.3F\nUptime: 3 days, 0 hours\n"
            "Total memory: 4096 MB  Free memory: 1900 MB"
        ),
        "leaf2": (
            "Arista cEOS\nSerial number: LFX2134567891\n"
            "Software image version: 4.27.3F\nUptime: 2 days, 5 hours\n"
            "Total memory: 4096 MB  Free memory: 1750 MB"
        ),
    },
    "show ip interface brief": {
        "spine1": (
            "Interface         IP Address         Status   Protocol  MTU\n"
            "Ethernet1         unassigned         up       up        9214\n"
            "Ethernet2         unassigned         up       up        9214\n"
            "Ethernet3         unassigned         up       up        9214\n"
            "Loopback0         10.0.0.11/32       up       up        65535\n"
            "Management1       192.168.0.11/24    up       up        1500"
        ),
        "spine2": (
            "Interface         IP Address         Status   Protocol  MTU\n"
            "Ethernet1         unassigned         up       up        9214\n"
            "Ethernet2         unassigned         up       up        9214\n"
            "Ethernet3         unassigned         up       up        9214\n"
            "Loopback0         10.0.0.12/32       up       up        65535\n"
            "Management1       192.168.0.12/24    up       up        1500"
        ),
        "leaf1": (
            "Interface         IP Address         Status   Protocol  MTU\n"
            "Ethernet1         unassigned         up       up        9214\n"
            "Ethernet2         unassigned         up       up        9214\n"
            "Ethernet3         unassigned         up       up        9214\n"
            "Loopback0         10.0.1.21/32       up       up        65535\n"
            "Management1       192.168.0.21/24    up       up        1500"
        ),
        "leaf2": (
            "Interface         IP Address         Status   Protocol  MTU\n"
            "Ethernet1         unassigned         up       up        9214\n"
            "Ethernet2         unassigned         up       up        9214\n"
            "Ethernet3         unassigned         down     down      9214\n"
            "Loopback0         10.0.1.22/32       up       up        65535\n"
            "Management1       192.168.0.22/24    up       up        1500"
        ),
    },
    "show bgp summary": {
        "spine1": (
            "BGP summary for VRF default — Router ID 10.0.0.11, AS 65001\n"
            "Neighbor    AS     MsgRcvd  MsgSent  Up/Down   State   PfxRcd\n"
            "10.1.1.1    65011  5432     5433     3d02h     Estab   150\n"
            "10.1.1.3    65012  4321     4322     3d02h     Estab   200"
        ),
        "spine2": (
            "BGP summary for VRF default — Router ID 10.0.0.12, AS 65001\n"
            "Neighbor    AS     MsgRcvd  MsgSent  Up/Down   State   PfxRcd\n"
            "10.1.2.1    65011  7654     7655     5d01h     Estab   150\n"
            "10.1.2.3    65012  6543     6544     5d01h     Estab   200"
        ),
        "leaf1": (
            "BGP summary for VRF default — Router ID 10.0.1.21, AS 65011\n"
            "Neighbor    AS     MsgRcvd  MsgSent  Up/Down   State   PfxRcd\n"
            "10.1.1.0    65001  5433     5432     3d01h     Estab   50\n"
            "10.1.2.0    65001  5434     5433     3d01h     Estab   50"
        ),
        "leaf2": (
            "BGP summary for VRF default — Router ID 10.0.1.22, AS 65012\n"
            "Neighbor    AS     MsgRcvd  MsgSent  Up/Down   State   PfxRcd\n"
            "10.1.1.2    65001  3210     3211     2d03h     Estab   50\n"
            "10.1.2.2    65001  0        0        0:00:00   Idle    0"
        ),
    },
}


def _mock_lookup(device: str, command: str) -> str:
    """Look up mock CLI output by device + command keyword."""
    device = device.lower()
    cmd = command.lower()
    for key, table in _MOCK.items():
        if key in cmd:
            return table.get(device, f"[mock] No data for {device}")
    return f"[mock] Command '{command}' not in mock data"


# ============================================================================
# SSH COLLECTION via Netmiko
# ============================================================================

def collect_via_ssh(device_name: str, command: str) -> str:
    """
    Run a show command on a device via SSH and return raw output.

    In mock mode the function returns pre-recorded output so the rest of
    the code path is identical to live — just flip USE_MOCK to test both.

    Args:
        device_name: spine1 | spine2 | leaf1 | leaf2
        command:     Any 'show' command (e.g. 'show ip interface brief')

    Returns:
        Raw CLI output as a string
    """
    if USE_MOCK:
        return _mock_lookup(device_name, command)

    try:
        from netmiko import ConnectHandler
    except ImportError:
        print("  netmiko not installed — pip install -r requirements.txt")
        print("  Falling back to mock data...")
        return _mock_lookup(device_name, command)

    cfg = DEVICE_CONFIG.get(device_name.lower())
    if not cfg:
        return f"Error: '{device_name}' not in DEVICE_CONFIG"

    try:
        print(f"  Connecting to {device_name} ({cfg['host']}) ...")
        with ConnectHandler(**cfg) as conn:
            output = conn.send_command(command)
        print(f"  Done ({len(output)} bytes)")
        return output
    except Exception as exc:
        print(f"  SSH error: {exc}")
        print("  Falling back to mock data...")
        return _mock_lookup(device_name, command)


# ============================================================================
# TJU API ANALYSIS
# ============================================================================

def analyze_with_tju(
    device_output: str,
    question: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """Feed raw CLI output into tju-llm and ask a question about it."""
    prompt = f"""You are a network engineer analyzing live device output.

DEVICE OUTPUT:
{device_output}

QUESTION: {question}

Give a concise, accurate answer based only on the output above."""

    try:
        return generate_text(
            prompt,
            model=model,
            temperature=0.2,
            max_tokens=400,
            timeout=60,
        )
    except TJUAPIError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error: {exc}"


# ============================================================================
# DEMO
# ============================================================================

def demo_interface_health():
    """Collect interface data from every device and ask tju-llm for issues."""
    mode = "MOCK" if USE_MOCK else "LIVE SSH"
    print(f"\n{'='*70}")
    print(f"INTERFACE HEALTH CHECK  [{mode}]")
    print(f"{'='*70}")

    for device in ["spine1", "spine2", "leaf1", "leaf2"]:
        print(f"\n[{device.upper()}]")
        raw = collect_via_ssh(device, "show ip interface brief")
        print(raw)
        analysis = analyze_with_tju(raw, "Are there any down interfaces? List them and suggest next steps.")
        print(f"AI: {analysis}")


def demo_bgp_health():
    """Collect BGP summaries from all devices and ask tju-llm for a roll-up."""
    mode = "MOCK" if USE_MOCK else "LIVE SSH"
    print(f"\n{'='*70}")
    print(f"BGP HEALTH CHECK  [{mode}]")
    print(f"{'='*70}")

    combined = ""
    for device in ["spine1", "spine2", "leaf1", "leaf2"]:
        raw = collect_via_ssh(device, "show bgp summary")
        combined += f"\n=== {device} ===\n{raw}\n"

    print("Collected BGP data from all devices. Asking tju-llm...")
    analysis = analyze_with_tju(
        combined,
        "Summarize BGP health. Are all sessions Established? Highlight any Idle or Active sessions.",
    )
    print(f"\nBGP Summary:\n{analysis}")


if __name__ == "__main__":
    mode = "MOCK DATA (no real devices needed)" if USE_MOCK else "LIVE SSH — real devices"
    print("🔧 Netmiko SSH + TJU API  |  Building AI Agents for Network Operations")
    print("=" * 70)
    print(f"Mode: {mode}")
    print("To use real devices: set USE_MOCK = False and update DEVICE_CONFIG")
    print("=" * 70)

    demo_interface_health()
    demo_bgp_health()

    print("\n" + "=" * 70)
    print("Key takeaways:")
    print("  1. collect_via_ssh() is the same code pattern used in production")
    print("  2. Netmiko handles Cisco IOS, Arista EOS, Juniper, and 30+ more")
    print("  3. Raw CLI output can go straight into tju-llm — no pre-parsing needed")
    print("  4. Flip USE_MOCK = False when you have real devices available")
    print("=" * 70)
