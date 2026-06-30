#!/usr/bin/env python3
"""
Lab 1 — Challenge 2 (SSH): Parse BGP Summary Output to JSON
AI Networking Workshop

Same goal as challenge_2_bgp_parser.py but the input comes
from a real device over SSH using Netmiko.

MODES:
    USE_MOCK = True   — pre-recorded output, no device needed (default)
    USE_MOCK = False  — SSHes into the device and runs the command live

RUN:
    python challenge_2_bgp_parser_ssh.py
"""

import requests
import json

# ============================================================================
# TOGGLE — flip to False + update DEVICE_CONFIG for a real device
# ============================================================================

USE_MOCK = True

DEVICE_CONFIG = {
    "host":        "192.168.0.22",   # leaf2 — has one Idle BGP session
    "device_type": "arista_eos",
    "username":    "admin",
    "password":    "admin",
    "port":        22,
}

COMMAND = "show bgp summary"

# ── Pre-recorded output (leaf2, Arista EOS) ───────────────────────────────
# leaf2 has one Established and one Idle session — good for demo

MOCK_OUTPUT = """\
BGP summary for VRF default — Router ID 10.0.1.22, AS 65012
Neighbor    AS     MsgRcvd  MsgSent  Up/Down   State   PfxRcd
10.1.1.2    65001  3210     3211     2d03h     Estab   50
10.1.2.2    65001  0        0        0:00:00   Idle    0"""


# ============================================================================
# SSH COLLECTION via Netmiko
# ============================================================================

def collect_via_ssh() -> str:
    """SSH into the device and run 'show bgp summary'."""
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
        print("  [MOCK] Using pre-recorded leaf2 BGP summary\n")
        return MOCK_OUTPUT
    return collect_via_ssh()


# ============================================================================
# OLLAMA — parse the CLI output into JSON
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
        print(f"❌ Model didn't return valid JSON. Raw:\n{raw[:300]}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


# ============================================================================
# CHALLENGE
# ============================================================================

PROMPT_TEMPLATE = """\
Parse this BGP summary output into JSON:

{cli_output}

Return a JSON object with:
- router_id: string
- local_as: integer
- neighbors: array of objects, each with:
    - ip: string
    - remote_as: integer
    - state: string  (e.g. "Established", "Idle", "Active")
    - uptime: string
    - prefixes_received: integer
"""


def run():
    mode = "MOCK DATA" if USE_MOCK else f"LIVE SSH → {DEVICE_CONFIG['host']}"
    print("=" * 60)
    print(f"Challenge 2 (SSH): BGP Parser  [{mode}]")
    print("=" * 60)

    # Step 1: collect from device (or mock)
    raw = get_raw_output()
    print(f"Raw output from '{COMMAND}':")
    print(raw)
    print()

    # Step 2: parse with Ollama
    print("Asking Ollama to parse it...\n")
    result = ask_ollama(PROMPT_TEMPLATE.format(cli_output=raw))

    if result:
        print("✅ Parsed JSON:")
        print(json.dumps(result, indent=2))

        # Step 3: act on the data
        neighbors = result.get("neighbors", [])
        down = [n for n in neighbors if n.get("state") != "Established"]
        print(f"\n📊 Total neighbors: {len(neighbors)}")
        if down:
            print("⚠️  Non-established sessions:")
            for n in down:
                print(f"   {n['ip']} (AS {n['remote_as']}) — {n['state']}")
        else:
            print("✅ All sessions Established")
    else:
        print("❌ Parse failed — tweak the prompt and try again.")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Set USE_MOCK = False and point DEVICE_CONFIG at a real device")
    print("  2. Change host to spine1 (192.168.0.11) — it has more neighbors")
    print("  3. Loop over all 4 devices and collect BGP from each one:")
    print("     for host in ['192.168.0.11','192.168.0.12','192.168.0.21','192.168.0.22']:")
    print("         DEVICE_CONFIG['host'] = host")
    print("         raw = collect_via_ssh()")
    print("-" * 60)


if __name__ == "__main__":
    run()
