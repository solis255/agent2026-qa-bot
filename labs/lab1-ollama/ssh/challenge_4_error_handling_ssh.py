#!/usr/bin/env python3
"""
Lab 1 — Challenge 4 (SSH): Error Handling with Real Device Output
AI Networking Workshop

Same goal as challenge_4_error_handling.py but errors come from
two places now: SSH connection failures AND bad device output.
Both need to be handled gracefully.

MODES:
    USE_MOCK = True   — pre-recorded output including a down port (default)
    USE_MOCK = False  — SSHes into real devices via Netmiko

RUN:
    python challenge_4_error_handling_ssh.py
"""

import requests
import json
import re

# ============================================================================
# TOGGLE — flip to False + update DEVICES for real connections
# ============================================================================

USE_MOCK = True

# Two devices — leaf2 has a real down interface (Ethernet3)
DEVICES = [
    {
        "label":       "leaf1",
        "host":        "192.168.0.21",
        "device_type": "arista_eos",
        "username":    "admin",
        "password":    "admin",
        "port":        22,
    },
    {
        "label":       "leaf2",
        "host":        "192.168.0.22",
        "device_type": "arista_eos",
        "username":    "admin",
        "password":    "admin",
        "port":        22,
    },
    {
        # Intentionally unreachable — tests SSH error handling
        "label":       "offline-device",
        "host":        "192.168.0.99",
        "device_type": "arista_eos",
        "username":    "admin",
        "password":    "admin",
        "port":        22,
    },
]

COMMAND = "show ip interface brief"

# ── Pre-recorded output ───────────────────────────────────────────────────

MOCK_OUTPUTS = {
    "leaf1": """\
Interface         IP Address         Status   Protocol  MTU
Ethernet1         unassigned         up       up        9214
Ethernet2         unassigned         up       up        9214
Ethernet3         unassigned         up       up        9214
Loopback0         10.0.1.21/32       up       up        65535
Management1       192.168.0.21/24    up       up        1500""",

    "leaf2": """\
Interface         IP Address         Status   Protocol  MTU
Ethernet1         unassigned         up       up        9214
Ethernet2         unassigned         up       up        9214
Ethernet3         unassigned         down     down      9214
Loopback0         10.0.1.22/32       up       up        65535
Management1       192.168.0.22/24    up       up        1500""",

    # Simulates a device that returned an error instead of output
    "offline-device": "% Connection timed out; there may be a routing problem",
}


# ============================================================================
# SSH COLLECTION via Netmiko (with error capture)
# ============================================================================

def collect_via_ssh(device: dict) -> tuple[str | None, str]:
    """
    SSH into a device and run the show command.

    Returns:
        (output, "")          — success
        (None, error_reason)  — connection or command failure
    """
    try:
        from netmiko import ConnectHandler
    except ImportError:
        return None, "netmiko not installed — pip install -r requirements.txt"

    cfg = {k: v for k, v in device.items() if k != "label"}
    try:
        with ConnectHandler(**cfg) as conn:
            output = conn.send_command(COMMAND, read_timeout=10)
        return output, ""
    except Exception as exc:
        return None, f"SSH error: {exc}"


def get_raw_output(device: dict) -> tuple[str | None, str]:
    """Return (output, error) from mock or live SSH."""
    if USE_MOCK:
        mock = MOCK_OUTPUTS.get(device["label"])
        if mock:
            return mock, ""
        return None, f"No mock data for {device['label']}"
    return collect_via_ssh(device)


# ============================================================================
# OLLAMA — parse with error recovery (upgraded helper)
# ============================================================================

def ask_ollama(prompt: str, model: str = "llama3.2:3b") -> tuple[dict | None, str]:
    """
    Send a prompt to Ollama.

    Returns:
        (dict, "")       — success
        (None, reason)   — failure with a human-readable reason
    """
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

        # Recovery 1: strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        # Recovery 2: grab first {...} block if model added preamble
        if not raw.startswith("{"):
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                raw = match.group()

        return json.loads(raw), ""

    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to Ollama — is it running? (ollama serve)"
    except Exception as e:
        return None, f"Unexpected error: {e}"


PROMPT_TEMPLATE = """\
Parse this network device interface output into JSON.
The device may have down interfaces or error messages — represent that faithfully.

Device: {label}
Output:
{cli_output}

Return a JSON object with:
- device: "{label}"
- parse_status: "ok" or "error"
- error_message: string or null  (if the output is an error, put it here)
- interfaces: array of objects (empty list if output is an error), each with:
    - name: string
    - admin_status: "up" or "down"
    - oper_status: "up", "down", or "unknown"
"""


# ============================================================================
# CHALLENGE
# ============================================================================

def process_device(device: dict) -> None:
    """Collect, parse, and report for a single device."""
    label = device["label"]
    print(f"── {label} ({device['host']}) ──")

    # Step 1: collect (SSH or mock)
    raw, ssh_error = get_raw_output(device)

    if ssh_error:
        # SSH itself failed — no output to parse
        print(f"   ❌ Collection failed: {ssh_error}")
        print("   ℹ️  Logging and moving on...\n")
        return

    # Step 2: parse with Ollama
    result, parse_error = ask_ollama(
        PROMPT_TEMPLATE.format(label=label, cli_output=raw)
    )

    if parse_error:
        print(f"   ❌ Parse failed: {parse_error}")
        print("   ℹ️  Logging and moving on...\n")
        return

    # Step 3: act on the result
    if result.get("parse_status") == "error":
        print(f"   ⚠️  Device returned an error: {result.get('error_message')}")
    else:
        interfaces = result.get("interfaces", [])
        down = [i for i in interfaces if i.get("oper_status") != "up"]
        print(f"   ✅ {len(interfaces)} interfaces parsed")
        if down:
            print(f"   ⚠️  Down: {', '.join(i['name'] for i in down)}")
        else:
            print("   ✅ All interfaces up")

    print()


def run():
    mode = "MOCK DATA" if USE_MOCK else "LIVE SSH"
    print("=" * 60)
    print(f"Challenge 4 (SSH): Error Handling  [{mode}]")
    print("=" * 60)
    print("Three scenarios: healthy device, down interface, unreachable device\n")

    for device in DEVICES:
        process_device(device)

    print("=" * 60)
    print("Error handling layers demonstrated:")
    print("  1. SSH failure     → caught in collect_via_ssh(), logged, skipped")
    print("  2. Device error    → Ollama sets parse_status='error', we handle it")
    print("  3. Bad JSON        → caught in ask_ollama(), returns (None, reason)")
    print("  4. Ollama offline  → ConnectionError caught, returns (None, reason)")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Set USE_MOCK = False — 'offline-device' will actually time out")
    print("     Watch how the SSH error is caught without crashing the script")
    print("  2. Add a retry loop around collect_via_ssh() (max 2 retries)")
    print("  3. Write failures to a log file:")
    print("     with open('failures.log', 'a') as f: f.write(f'{label}: {error}\\n')")
    print("-" * 60)


if __name__ == "__main__":
    run()
