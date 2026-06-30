#!/usr/bin/env python3
"""
Lab 1 — Challenge 4: Robust JSON Parsing with Error Recovery
Building AI Agents for Network Operations

GOAL:
    Handle the two things that can go wrong when asking an LLM
    for JSON:
      1. The device output itself is an error (flapping, unknown state)
      2. The model returns malformed JSON (markdown fences, extra text)

WHY THIS MATTERS:
    Production automation can't crash on bad input. You need your
    parser to degrade gracefully and tell you *why* it failed —
    not just blow up with an exception at 3 AM.

RUN:
    python challenge_4_error_handling.py
"""

import requests
import json
import re


# ── Helper (with better error recovery than challenges 1-3) ───────────────

def ask_ollama(prompt: str, model: str = "llama3.2:3b") -> tuple[dict | None, str]:
    """
    Send a prompt to Ollama and return (parsed_dict, error_message).

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

        # Recovery step 1: strip markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        # Recovery step 2: grab the first {...} block if there's extra text
        if not raw.startswith("{"):
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                raw = match.group()

        return json.loads(raw), ""

    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e} | raw: {raw[:200]}"
    except requests.exceptions.ConnectionError:
        return None, "Cannot connect to Ollama — is it running? (ollama serve)"
    except Exception as e:
        return None, f"Unexpected error: {e}"


# ── Three scenarios ───────────────────────────────────────────────────────

# Scenario A: device output has an error state
ERROR_OUTPUT = """
GigabitEthernet0/1 is up, line protocol is down (err-disabled)
  Hardware is iGbE, address is 0000.0c07.ac01
  err-disabled reason: port-security violation
"""

# Scenario B: ambiguous/unknown status
UNKNOWN_OUTPUT = """
GigabitEthernet0/2 is up, line protocol is unknown
  Last flap 00:00:03 ago
"""

# Scenario C: completely empty / no data
EMPTY_OUTPUT = "% No interface information available"


def parse_with_recovery(label: str, device_output: str) -> None:
    """Run one scenario and print the result."""
    print(f"── {label} ──")
    print(f"   Input: {device_output.strip()[:80]}")

    prompt = f"""Parse this network interface output into JSON.
The interface may be in an error or unknown state — represent that faithfully.

{device_output}

Return a JSON object with:
- interface: string or null
- admin_status: "up", "down", or "unknown"
- oper_status: "up", "down", "err-disabled", or "unknown"
- error_reason: string or null  (reason for err-disabled, or null if none)
- warning: string or null  (any notable condition, or null)
"""

    result, error = ask_ollama(prompt)

    if result:
        print(f"   ✅ {json.dumps(result)}")
    else:
        print(f"   ❌ Parse failed — {error}")
        # In production you'd log this and move on, not crash
        print("   ℹ️  Continuing to next device...")

    print()


def run():
    print("=" * 60)
    print("Challenge 4: Error Handling & Graceful Recovery")
    print("=" * 60)
    print()

    parse_with_recovery("Error-disabled port",   ERROR_OUTPUT)
    parse_with_recovery("Flapping / unknown",    UNKNOWN_OUTPUT)
    parse_with_recovery("No data available",     EMPTY_OUTPUT)

    print("=" * 60)
    print("Key patterns used in ask_ollama():")
    print("  1. Strip markdown fences (``` blocks)")
    print("  2. Grab first {...} block if model adds preamble text")
    print("  3. Return (result, error) tuple — never raise, never crash")
    print("  4. Caller decides what to do with a failure")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Add a 4th scenario: a device that returned binary garbage")
    print("  2. Wrap parse_with_recovery() in a retry loop (max 3 attempts)")
    print("  3. Write the failed parses to a log file instead of printing them")
    print("-" * 60)


if __name__ == "__main__":
    run()
