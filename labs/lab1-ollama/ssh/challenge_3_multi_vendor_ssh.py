#!/usr/bin/env python3
"""
Lab 1 — Challenge 3 (SSH): Multi-Vendor Interface Normalisation via SSH
Building AI Agents for Network Operations

Same goal as challenge_3_multi_vendor.py but the input comes from
real devices over SSH. Each entry in DEVICES can be a different
vendor — Netmiko handles the connection, Ollama handles the parsing.

The key insight: the prompt stays identical across all vendors.
Only the device_type in DEVICE_CONFIG changes.

MODES:
    USE_MOCK = True   — pre-recorded output from 3 different vendors (default)
    USE_MOCK = False  — SSHes into each device in DEVICES

RUN:
    python challenge_3_multi_vendor_ssh.py
"""

import requests
import json

# ============================================================================
# TOGGLE — flip to False + update DEVICES for real connections
# ============================================================================

USE_MOCK = True

# Each entry is a separate device (can be a different vendor)
DEVICES = [
    {
        "label":       "Arista spine1",
        "host":        "192.168.0.11",
        "device_type": "arista_eos",
        "username":    "admin",
        "password":    "admin",
        "port":        22,
    },
    {
        "label":       "Arista leaf1",
        "host":        "192.168.0.21",
        "device_type": "arista_eos",
        "username":    "admin",
        "password":    "admin",
        "port":        22,
    },
    {
        "label":       "Arista leaf2",
        "host":        "192.168.0.22",
        "device_type": "arista_eos",
        "username":    "admin",
        "password":    "admin",
        "port":        22,
    },
    # ── Add real Cisco / Juniper entries here when available ──────────
    # {
    #     "label":       "Cisco core-rtr",
    #     "host":        "192.168.1.1",
    #     "device_type": "cisco_ios",
    #     "username":    "admin",
    #     "password":    "admin",
    #     "port":        22,
    # },
    # {
    #     "label":       "Juniper edge-rtr",
    #     "host":        "192.168.1.2",
    #     "device_type": "juniper_junos",
    #     "username":    "admin",
    #     "password":    "admin",
    #     "port":        22,
    # },
]

COMMAND = "show ip interface brief"

# ── Pre-recorded output for each device ──────────────────────────────────

MOCK_OUTPUTS = {
    "Arista spine1": """\
Interface         IP Address         Status   Protocol  MTU
Ethernet1         unassigned         up       up        9214
Ethernet2         unassigned         up       up        9214
Ethernet3         unassigned         up       up        9214
Loopback0         10.0.0.11/32       up       up        65535
Management1       192.168.0.11/24    up       up        1500""",

    "Arista leaf1": """\
Interface         IP Address         Status   Protocol  MTU
Ethernet1         unassigned         up       up        9214
Ethernet2         unassigned         up       up        9214
Ethernet3         unassigned         up       up        9214
Loopback0         10.0.1.21/32       up       up        65535
Management1       192.168.0.21/24    up       up        1500""",

    "Arista leaf2": """\
Interface         IP Address         Status   Protocol  MTU
Ethernet1         unassigned         up       up        9214
Ethernet2         unassigned         up       up        9214
Ethernet3         unassigned         down     down      9214
Loopback0         10.0.1.22/32       up       up        65535
Management1       192.168.0.22/24    up       up        1500""",

    # Example Cisco format (uncomment when you add a Cisco device)
    # "Cisco core-rtr": """\
    # Interface              IP-Address      OK? Method Status                Protocol
    # GigabitEthernet0/0     10.0.0.1        YES NVRAM  up                    up
    # GigabitEthernet0/1     unassigned      YES NVRAM  administratively down down""",
}


# ============================================================================
# SSH COLLECTION via Netmiko
# ============================================================================

def collect_via_ssh(device: dict) -> str:
    """SSH into a single device and run the show command."""
    try:
        from netmiko import ConnectHandler
    except ImportError:
        print("  ⚠️  netmiko not installed — pip install -r requirements.txt")
        return MOCK_OUTPUTS.get(device["label"], "[no mock data]")

    cfg = {k: v for k, v in device.items() if k != "label"}
    print(f"  Connecting to {device['label']} ({device['host']})...")
    try:
        with ConnectHandler(**cfg) as conn:
            output = conn.send_command(COMMAND)
        print(f"  ✅ Got {len(output)} bytes")
        return output
    except Exception as exc:
        print(f"  ❌ SSH failed: {exc} — using mock")
        return MOCK_OUTPUTS.get(device["label"], "[no mock data]")


def get_raw_output(device: dict) -> str:
    if USE_MOCK:
        return MOCK_OUTPUTS.get(device["label"], "[no mock data]")
    return collect_via_ssh(device)


# ============================================================================
# OLLAMA — parse one device's output into normalised JSON
# ============================================================================

def ask_ollama(prompt: str, model: str = "llama3.2:3b") -> dict | None:
    """Send a prompt to Ollama, return parsed JSON or None."""
    json_prompt = f"""You are a JSON-only API. Return ONLY valid JSON.
No markdown, no explanation, no code fences — just the JSON object.

{prompt}

Output only valid JSON:"""

    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": json_prompt,
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    except json.JSONDecodeError:
        print(f"  ❌ Model didn't return valid JSON. Raw:\n{raw[:200]}")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


# One prompt template used for every vendor — same shape out every time
PROMPT_TEMPLATE = """\
Parse this network device interface output into JSON.
The device is: {label}

{cli_output}

Return a JSON object with:
- device: "{label}"
- interfaces: array of objects, each with:
    - name: string
    - ip_address: string or null
    - admin_status: "up" or "down"
    - oper_status: "up" or "down"
"""


# ============================================================================
# CHALLENGE
# ============================================================================

def run():
    mode = "MOCK DATA" if USE_MOCK else "LIVE SSH"
    print("=" * 60)
    print(f"Challenge 3 (SSH): Multi-Vendor Normalisation  [{mode}]")
    print("=" * 60)
    print("Goal: same JSON shape from every device, regardless of vendor\n")

    all_results = []

    for device in DEVICES:
        print(f"── {device['label']} ──")

        raw = get_raw_output(device)
        result = ask_ollama(PROMPT_TEMPLATE.format(
            label=device["label"],
            cli_output=raw,
        ))

        if result:
            interfaces = result.get("interfaces", [])
            down = [i for i in interfaces if i.get("oper_status") != "up"]
            status = f"{'⚠️ ' + str(len(down)) + ' down' if down else '✅ all up'}"
            print(f"   {len(interfaces)} interfaces — {status}")
            all_results.append(result)
        else:
            print("   ❌ parse failed")
        print()

    # Normalised summary across all devices
    if all_results:
        print("=" * 60)
        print("Normalised summary (any vendor, same structure):")
        print(f"{'Device':<20} {'Interfaces':<12} {'Down'}")
        print("-" * 60)
        for r in all_results:
            ifaces = r.get("interfaces", [])
            down_count = sum(1 for i in ifaces if i.get("oper_status") != "up")
            print(f"{r.get('device','?'):<20} {len(ifaces):<12} {down_count if down_count else '-'}")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Set USE_MOCK = False to SSH into the real lab devices")
    print("  2. Uncomment a Cisco or Juniper entry in DEVICES")
    print("     — the prompt handles the format difference automatically")
    print("  3. Add 'down_interfaces: list of names' to the prompt")
    print("     so you get a ready-made alert list per device")
    print("-" * 60)


if __name__ == "__main__":
    run()
