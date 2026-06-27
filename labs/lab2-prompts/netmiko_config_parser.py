#!/usr/bin/env python3
"""
Lab 2: Netmiko SSH Config Fetch + RACE Prompt Parsing
AI Networking Workshop

WORKSHOP MODE:  USE_MOCK = True  (works without any devices)
POST-WORKSHOP:  Set USE_MOCK = False and update DEVICE_CONFIG

What this shows:
- Fetch running configs and show output via SSH (Netmiko)
- Apply RACE structured prompts to real device output
- Get clean, machine-readable JSON back from raw CLI text
"""

import json
import requests

# ============================================================================
# TOGGLE: Mock data vs live SSH
# ============================================================================

USE_MOCK = True  # Flip to False with real devices after the workshop

DEVICE_CONFIG = {
    "spine1": {"device_type": "arista_eos", "host": "192.168.0.11", "username": "admin", "password": "admin", "port": 22},
    "leaf1":  {"device_type": "arista_eos", "host": "192.168.0.21", "username": "admin", "password": "admin", "port": 22},
    "leaf2":  {"device_type": "arista_eos", "host": "192.168.0.22", "username": "admin", "password": "admin", "port": 22},
}

# ============================================================================
# MOCK DATA — realistic Arista EOS interface config snippets
# ============================================================================

MOCK_INTERFACE_CONFIGS = {
    "spine1": """
interface Ethernet1
   description to_leaf1
   no switchport
   ip address 10.1.1.0/31
   bfd interval 300 min-rx 300 multiplier 3
!
interface Ethernet2
   description to_leaf2
   no switchport
   ip address 10.1.2.0/31
   bfd interval 300 min-rx 300 multiplier 3
!
interface Management1
   ip address 192.168.0.11/24
!
interface Loopback0
   description router_id
   ip address 10.0.0.11/32
""",
    "leaf1": """
interface Ethernet1
   description to_spine1
   no switchport
   ip address 10.1.1.1/31
!
interface Ethernet2
   description to_spine2
   no switchport
   ip address 10.1.2.1/31
!
interface Ethernet3
   description server_rack_1
   switchport access vlan 100
   spanning-tree portfast
!
interface Management1
   ip address 192.168.0.21/24
!
interface Loopback0
   description router_id
   ip address 10.0.1.21/32
""",
    "leaf2": """
interface Ethernet1
   description to_spine1
   no switchport
   ip address 10.1.1.3/31
!
interface Ethernet2
   description to_spine2
   no switchport
   ip address 10.1.2.3/31
!
interface Ethernet3
   description server_rack_2
   switchport access vlan 200
   shutdown
!
interface Management1
   ip address 192.168.0.22/24
!
interface Loopback0
   description router_id
   ip address 10.0.1.22/32
""",
}

MOCK_SHOW_INT_STATUS = {
    "spine1": """
Port         Name            Status    Vlan  Duplex  Speed   Type
Et1          to_leaf1        connected routed full    10G     Ebraided
Et2          to_leaf2        connected routed full    10G     Ebraided
Et3          to_spine2       connected routed full    40G     Ebraided
Ma1          oob_management  connected 1     full    1G      10/100/1000
""",
    "leaf1": """
Port         Name            Status       Vlan  Duplex  Speed  Type
Et1          to_spine1       connected    routed full   10G    Ebraided
Et2          to_spine2       connected    routed full   10G    Ebraided
Et3          server_rack_1   connected    100   full    1G     10/100/1000
Ma1          oob_management  connected    1     full    1G     10/100/1000
""",
    "leaf2": """
Port         Name            Status       Vlan  Duplex  Speed  Type
Et1          to_spine1       connected    routed full   10G    Ebraided
Et2          to_spine2       connected    routed full   10G    Ebraided
Et3          server_rack_2   disabled     200   full    1G     10/100/1000
Ma1          oob_management  connected    1     full    1G     10/100/1000
""",
}


# ============================================================================
# SSH DATA FETCH via Netmiko
# ============================================================================

def fetch_via_ssh(device_name: str, command: str) -> str:
    """
    Run a command on a device via SSH (or return mock data).

    Args:
        device_name: Device hostname key in DEVICE_CONFIG
        command:     show command or 'show running-config' variant

    Returns:
        Raw CLI output as string
    """
    if USE_MOCK:
        return _mock_lookup(device_name, command)

    try:
        from netmiko import ConnectHandler
    except ImportError:
        print("  netmiko not installed — pip install netmiko")
        return _mock_lookup(device_name, command)

    cfg = DEVICE_CONFIG.get(device_name.lower())
    if not cfg:
        return f"Error: '{device_name}' not in DEVICE_CONFIG"

    try:
        print(f"  SSH → {device_name} ({cfg['host']}) ...")
        with ConnectHandler(**cfg) as conn:
            output = conn.send_command(command, read_timeout=30)
        print(f"  Done ({len(output)} bytes)")
        return output
    except Exception as exc:
        print(f"  SSH error: {exc}  — using mock data")
        return _mock_lookup(device_name, command)


def _mock_lookup(device: str, command: str) -> str:
    device = device.lower()
    cmd = command.lower()
    if "running-config" in cmd or "interfaces" in cmd:
        return MOCK_INTERFACE_CONFIGS.get(device, f"[mock] no config for {device}")
    if "interface status" in cmd or "int status" in cmd:
        return MOCK_SHOW_INT_STATUS.get(device, f"[mock] no status for {device}")
    return f"[mock] command '{command}' not mocked for {device}"


# ============================================================================
# OLLAMA LLM CALL
# ============================================================================

def call_llm(prompt: str, model: str = "llama3.2:3b", temperature: float = 0.2) -> str:
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": temperature, "num_predict": 800}},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "Error: Ollama not running — try: ollama serve"
    except Exception as exc:
        return f"Error: {exc}"


# ============================================================================
# RACE PROMPTS applied to real (or mock) SSH data
# ============================================================================

def parse_interfaces_race(raw_config: str) -> str:
    """
    RACE prompt to extract all interfaces from a running-config block.

    Returns JSON array of interface objects.
    """
    prompt = f"""You are a network automation engineer building a device inventory system.

TASK: Parse the Arista EOS running-config excerpt below and return every interface as a JSON array.

OUTPUT FORMAT (array of objects):
[
  {{
    "interface": "string",
    "description": "string or null",
    "ip_address": "string or null",
    "mode": "routed | access | trunk | loopback | management",
    "vlan": "integer or null",
    "shutdown": true | false
  }}
]

EXAMPLE INPUT:
interface Ethernet1
   description to_core
   no switchport
   ip address 10.0.0.1/31
!
interface Ethernet2
   description servers
   switchport access vlan 10
!

EXAMPLE OUTPUT:
[
  {{"interface": "Ethernet1", "description": "to_core", "ip_address": "10.0.0.1/31", "mode": "routed", "vlan": null, "shutdown": false}},
  {{"interface": "Ethernet2", "description": "servers", "ip_address": null, "mode": "access", "vlan": 10, "shutdown": false}}
]

CONSTRAINTS:
- Output ONLY a valid JSON array, no markdown fences, no explanation
- If no description is present, use null
- shutdown = true if the 'shutdown' keyword appears under that interface

NOW PARSE THIS CONFIG:
{raw_config}

Output JSON array:"""

    return call_llm(prompt)


def audit_disabled_interfaces_race(device: str, raw_status: str) -> str:
    """
    RACE prompt to identify disabled/problematic interfaces and suggest actions.
    """
    prompt = f"""You are a senior network engineer auditing a data-center switch.

TASK: Review the interface status table for {device} and produce an audit report as JSON.

OUTPUT FORMAT:
{{
  "device": "string",
  "total_interfaces": integer,
  "healthy": integer,
  "issues": [
    {{
      "interface": "string",
      "status": "string",
      "description": "string",
      "recommended_action": "string"
    }}
  ],
  "overall_health": "healthy | degraded | critical"
}}

EXAMPLE INPUT:
Port  Name         Status     Vlan
Et1   uplink       connected  routed
Et2   servers      disabled   100

EXAMPLE OUTPUT:
{{
  "device": "leaf1",
  "total_interfaces": 2,
  "healthy": 1,
  "issues": [{{"interface": "Et2", "status": "disabled", "description": "servers", "recommended_action": "Verify port-channel or server NIC"}}],
  "overall_health": "degraded"
}}

CONSTRAINTS:
- Output ONLY valid JSON, no markdown, no extra text
- "connected" or "up" = healthy; anything else = an issue
- overall_health: healthy (0 issues), degraded (1-2), critical (3+)

INTERFACE STATUS TO AUDIT:
{raw_status}

Output JSON:"""

    return call_llm(prompt)


# ============================================================================
# DEMO
# ============================================================================

def demo_config_parser():
    mode = "MOCK" if USE_MOCK else "LIVE SSH"
    print(f"\n{'='*70}")
    print(f"RACE CONFIG PARSER  [{mode}]")
    print(f"{'='*70}")

    for device in ["spine1", "leaf1", "leaf2"]:
        print(f"\n[{device.upper()}] — parsing interface config via SSH")
        raw = fetch_via_ssh(device, "show running-config interfaces")
        result = parse_interfaces_race(raw)

        try:
            parsed = json.loads(result)
            print(f"  Parsed {len(parsed)} interfaces:")
            for intf in parsed:
                flag = " *** SHUTDOWN ***" if intf.get("shutdown") else ""
                print(f"    {intf['interface']:<15} {intf.get('mode','?'):<12} {intf.get('ip_address') or intf.get('vlan') or ''}{flag}")
        except json.JSONDecodeError:
            print(f"  Raw result:\n{result}")


def demo_interface_audit():
    mode = "MOCK" if USE_MOCK else "LIVE SSH"
    print(f"\n{'='*70}")
    print(f"INTERFACE AUDIT  [{mode}]")
    print(f"{'='*70}")

    for device in ["leaf1", "leaf2"]:
        print(f"\n[{device.upper()}]")
        raw = fetch_via_ssh(device, "show interfaces status")
        result = audit_disabled_interfaces_race(device, raw)

        try:
            audit = json.loads(result)
            health = audit.get("overall_health", "?").upper()
            issues = audit.get("issues", [])
            print(f"  Health: {health}  |  Issues: {len(issues)}")
            for issue in issues:
                print(f"    {issue['interface']}: {issue['status']} — {issue['recommended_action']}")
        except json.JSONDecodeError:
            print(f"  Raw result:\n{result}")


if __name__ == "__main__":
    mode = "MOCK DATA (no real devices needed)" if USE_MOCK else "LIVE SSH — real devices"
    print("🎯 RACE + Netmiko SSH  |  AI Networking Workshop")
    print("=" * 70)
    print(f"Mode: {mode}")
    print("To use real devices: set USE_MOCK = False and update DEVICE_CONFIG")
    print("=" * 70)

    demo_config_parser()
    demo_interface_audit()

    print("\n" + "=" * 70)
    print("Key takeaways:")
    print("  1. Same RACE prompts work on real device output — no changes needed")
    print("  2. fetch_via_ssh() is a production-ready wrapper around Netmiko")
    print("  3. Structured prompts + real data = reliable JSON automation")
    print("  4. Flip USE_MOCK = False when real devices are available")
    print("=" * 70)
