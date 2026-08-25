#!/usr/bin/env python3
"""
Lab 1 — Challenge 2: Parse BGP Summary Output to JSON
Building AI Agents for Network Operations

GOAL:
    Feed raw 'show bgp summary' output to tju-llm and get back
    a structured list of neighbors you can loop over in code.

WHY THIS MATTERS:
    BGP troubleshooting means checking many neighbors across many
    devices. With JSON output you can filter, sort, and alert
    programmatically — no more reading walls of text.

RUN:
    python challenge_2_bgp_parser.py
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
        print(f"❌ Model didn't return valid JSON. Raw output:\n{raw[:300]}")
        return None
    except TJUAPIError as e:
        print(f"❌ Error: {e}")
        return None


# ── Challenge ─────────────────────────────────────────────────────────────

# Real-looking Arista BGP summary output
BGP_OUTPUT = """
BGP summary for VRF default — Router ID 10.0.0.11, AS 65001
Neighbor    AS     MsgRcvd  MsgSent  Up/Down   State   PfxRcd
10.1.1.1    65011  5432     5433     3d02h     Estab   150
10.1.1.3    65012  4321     4322     3d02h     Estab   200
10.1.2.0    65013  0        0        0:00:00   Idle    0
"""

PROMPT = f"""Parse this BGP summary output into JSON:

{BGP_OUTPUT}

Return a JSON object with:
- router_id: string
- local_as: integer
- neighbors: array of objects, each with:
    - ip: string
    - remote_as: integer
    - state: string  ("Established", "Idle", "Active", etc.)
    - uptime: string
    - prefixes_received: integer
"""


def run():
    print("=" * 60)
    print("Challenge 2: BGP Summary Parser")
    print("=" * 60)
    print("\nInput (raw CLI output):")
    print(BGP_OUTPUT)
    print("Asking tju-llm to parse it...\n")

    result = ask_tju(PROMPT)

    if result:
        print("✅ Parsed JSON:")
        print(json.dumps(result, indent=2))

        # Use the data — find any non-Established neighbors
        neighbors = result.get("neighbors", [])
        down = [n for n in neighbors if n.get("state") != "Established"]

        print(f"\n📊 Total neighbors: {len(neighbors)}")
        if down:
            print(f"⚠️  Non-established sessions:")
            for n in down:
                print(f"   {n['ip']} — {n['state']}")
        else:
            print("✅ All sessions Established")
    else:
        print("❌ Challenge failed — tweak the prompt and try again.")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Add a 4th neighbor in 'Active' state to BGP_OUTPUT and re-run")
    print("  2. Change the filter to find neighbors with prefixes_received == 0")
    print("  3. Try parsing Cisco IOS 'show ip bgp summary' format instead")
    print("-" * 60)


if __name__ == "__main__":
    run()
