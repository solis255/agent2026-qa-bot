#!/usr/bin/env python3
"""
Lab 1 — Challenge 1 (SSH): Parse Interface Output to JSON
Building AI Agents for Network Operations

Same goal as challenge_1_interface_parser.py but the input comes
from a real device over SSH using Netmiko instead of a hardcoded string.

MODES:
    USE_MOCK = True   — pre-recorded output, no device needed (default)
    USE_MOCK = False  — SSHes into the device and runs the command live

RUN:
    python challenge_1_interface_parser_ssh.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.tju_llm_client import DEFAULT_MODEL, TJUAPIError, generate_text

# ============================================================================
# TOGGLE — flip to False + update DEVICE_CONFIG for a real device
# ============================================================================

USE_MOCK = True

DEVICE_CONFIG = {
    "host":        "192.168.0.22",   # leaf2 — has Ethernet3 down (good demo)
    "device_type": "arista_eos",
    "username":    "admin",
    "password":    "admin",
    "port":        22,
}

COMMAND = "show ip interface brief"

# ── Pre-recorded output (leaf2, Arista EOS) ───────────────────────────────

MOCK_OUTPUT = """\
Interface         IP Address         Status   Protocol  MTU
Ethernet1         unassigned         up       up        9214
Ethernet2         unassigned         up       up        9214
Ethernet3         unassigned         down     down      9214
Loopback0         10.0.1.22/32       up       up        65535
Management1       192.168.0.22/24    up       up        1500"""


# ============================================================================
# SSH COLLECTION via Netmiko
# ============================================================================

def collect_via_ssh() -> str:
    """SSH into the device and run the show command."""
    try:
        from netmiko import ConnectHandler
    except ImportError:
        print("  ⚠️  netmiko not installed — pip install -r requirements.txt")
        print("  Falling back to mock data...\n")
        return MOCK_OUTPUT

    print(f"  Connecting to {DEVICE_CONFIG['host']} ({DEVICE_CONFIG['device_type']})...")
    try:
        with ConnectHandler(**DEVICE_CONFIG) as conn:
            output = conn.send_command(COMMAND)
        print(f"  ✅ Got {len(output)} bytes from device\n")
        return output
    except Exception as exc:
        print(f"  ❌ SSH failed: {exc}")
        print("  Falling back to mock data...\n")
        return MOCK_OUTPUT


def get_raw_output() -> str:
    if USE_MOCK:
        print("  [MOCK] Using pre-recorded leaf2 output\n")
        return MOCK_OUTPUT
    return collect_via_ssh()


# ============================================================================
# TJU API — parse the CLI output into JSON
# ============================================================================

def ask_tju(prompt: str, model: str = DEFAULT_MODEL) -> dict | None:
    """Send a prompt to the TJU API, return parsed JSON or None."""
    json_prompt = f"""You are a JSON-only API. Return ONLY valid JSON.
No markdown, no explanation, no code fences — just the JSON object.

{prompt}

Output only valid JSON:"""

    try:
        raw = generate_text(
            json_prompt,
            model=model,
            temperature=0.1,
            max_tokens=800,
            timeout=30,
        )

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    except json.JSONDecodeError:
        print(f"❌ Model didn't return valid JSON. Raw:\n{raw[:300]}")
        return None
    except TJUAPIError as e:
        print(f"❌ Error: {e}")
        return None


# ============================================================================
# CHALLENGE
# ============================================================================

PROMPT_TEMPLATE = """\
Parse this network device 'show ip interface brief' output into JSON:

{cli_output}

Return a JSON object with:
- interfaces: array of objects, each with:
    - name: string
    - ip_address: string or null
    - admin_status: "up" or "down"
    - oper_status: "up" or "down"
    - mtu: integer or null
"""


def run():
    mode = "MOCK DATA" if USE_MOCK else f"LIVE SSH → {DEVICE_CONFIG['host']}"
    print("=" * 60)
    print(f"Challenge 1 (SSH): Interface Parser  [{mode}]")
    print("=" * 60)

    # Step 1: collect from device (or mock)
    raw = get_raw_output()
    print(f"Raw output from '{COMMAND}':")
    print(raw)
    print()

    # Step 2: parse with tju-llm
    print("Asking tju-llm to parse it...\n")
    result = ask_tju(PROMPT_TEMPLATE.format(cli_output=raw))

    if result:
        print("✅ Parsed JSON:")
        print(json.dumps(result, indent=2))

        # Step 3: act on the data
        interfaces = result.get("interfaces", [])
        down = [i for i in interfaces if i.get("oper_status") != "up"]
        print(f"\n📊 Total interfaces: {len(interfaces)}")
        if down:
            print("⚠️  Down interfaces:")
            for i in down:
                print(f"   {i['name']} — oper: {i['oper_status']}")
        else:
            print("✅ All interfaces up")
    else:
        print("❌ Parse failed — tweak the prompt and try again.")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Set USE_MOCK = False and point DEVICE_CONFIG at a real device")
    print("  2. Change the host to leaf1 (192.168.0.21) — all interfaces up")
    print("     vs leaf2 (192.168.0.22) — Ethernet3 is down. See the difference.")
    print("  3. Try device_type = 'cisco_ios' against a Cisco device")
    print("     The prompt stays the same — tju-llm handles the format difference")
    print("-" * 60)


if __name__ == "__main__":
    run()
