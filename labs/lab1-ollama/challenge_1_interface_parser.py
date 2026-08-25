#!/usr/bin/env python3
"""
Lab 1 — Challenge 1: Parse Interface Output to JSON
Building AI Agents for Network Operations

GOAL:
    Get tju-llm to read raw Cisco 'show interface' output and
    return it as structured JSON your code can work with.

WHY THIS MATTERS:
    Network devices return unstructured text. To automate anything
    you need to convert that text into data. LLMs can do this
    without brittle regex parsers.

RUN:
    python challenge_1_interface_parser.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.tju_llm_client import DEFAULT_MODEL, TJUAPIError, generate_text


# ── Helper ────────────────────────────────────────────────────────────────

def ask_tju(prompt: str, model: str = DEFAULT_MODEL) -> dict | None:
    """
    Send a prompt to the TJU API and try to parse the response as JSON.

    Returns a dict on success, or None if the response isn't valid JSON.
    """
    # Wrap the prompt so the model knows to return ONLY JSON
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

        # Strip markdown code fences if the model added them anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        return json.loads(raw)

    except json.JSONDecodeError:
        print(f"❌ Model didn't return valid JSON. Raw output:\n{raw[:300]}")
        return None
    except TJUAPIError as e:
        print(f"❌ Error: {e}")
        return None


# ── Challenge ─────────────────────────────────────────────────────────────

# Raw text from a Cisco router — exactly what you'd see over SSH
INTERFACE_OUTPUT = """
GigabitEthernet0/1 is up, line protocol is up
  Hardware is iGbE, address is 0000.0c07.ac01
  Internet address is 10.0.0.1/24
  MTU 1500 bytes, BW 1000000 Kbit/sec
"""

PROMPT = f"""Parse this Cisco interface output into JSON:

{INTERFACE_OUTPUT}

Return a JSON object with exactly these fields:
- interface: string  (e.g. "GigabitEthernet0/1")
- admin_status: "up" or "down"
- oper_status: "up" or "down"
- ip_address: string or null  (e.g. "10.0.0.1")
- subnet_mask: string or null  (e.g. "255.255.255.0")
- mac_address: string  (e.g. "0000.0c07.ac01")
- mtu: integer  (e.g. 1500)
"""


def run():
    print("=" * 60)
    print("Challenge 1: Interface Parser")
    print("=" * 60)
    print("\nInput (raw CLI output):")
    print(INTERFACE_OUTPUT)
    print("Asking tju-llm to parse it...\n")

    result = ask_tju(PROMPT)

    if result:
        print("✅ Parsed JSON:")
        print(json.dumps(result, indent=2))

        # Quick validation — did we get the key fields?
        expected = ["interface", "admin_status", "oper_status", "ip_address", "mtu"]
        missing = [f for f in expected if f not in result]
        if missing:
            print(f"\n⚠️  Missing fields: {missing}")
        else:
            print("\n✅ All expected fields present!")
    else:
        print("❌ Challenge failed — tweak the prompt and try again.")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Change INTERFACE_OUTPUT to a 'down' interface and re-run")
    print("  2. Add an 'error_counter' field to the prompt and see if it extracts it")
    print("  3. Try an Arista or Juniper interface line instead of Cisco")
    print("-" * 60)


if __name__ == "__main__":
    run()
