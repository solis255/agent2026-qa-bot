#!/usr/bin/env python3
"""
Lab 1 — Challenge 3: Multi-Vendor Interface Normalisation
Building AI Agents for Network Operations

GOAL:
    Parse interface status lines from three different vendors
    (Cisco, Arista, Juniper) into a single common JSON format.

WHY THIS MATTERS:
    Real networks are multi-vendor. Writing a separate parser for
    each vendor is painful. An LLM can normalize different CLI
    styles into one consistent structure with a single prompt.

RUN:
    python challenge_3_multi_vendor.py
"""

import requests
import json


# ── Helper ────────────────────────────────────────────────────────────────

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
        print(f"❌ Model didn't return valid JSON. Raw output:\n{raw[:300]}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


# ── Challenge ─────────────────────────────────────────────────────────────

# The same interface status expressed in three different vendor CLIs
VENDORS = {
    "Cisco IOS":    "GigabitEthernet0/1 is up, line protocol is up",
    "Arista EOS":   "Ethernet1 is up, line protocol is up (connected)",
    "Juniper JunOS":"ge-0/0/1.0             up    up",
}

# One prompt template — we just swap in the vendor name and raw output
PROMPT_TEMPLATE = """Parse this {vendor} interface status line into JSON:

{output}

Return a JSON object with exactly these fields:
- vendor: "{vendor}"
- interface: string  (the interface name)
- admin_status: "up" or "down"
- oper_status: "up" or "down"
"""


def run():
    print("=" * 60)
    print("Challenge 3: Multi-Vendor Parser")
    print("=" * 60)
    print("\nGoal: same JSON shape from three different CLI formats\n")

    results = []

    for vendor, cli_output in VENDORS.items():
        print(f"── {vendor} ──")
        print(f"   Input:  {cli_output}")

        prompt = PROMPT_TEMPLATE.format(vendor=vendor, output=cli_output)
        result = ask_ollama(prompt)

        if result:
            print(f"   Output: {json.dumps(result)}")
            results.append(result)
        else:
            print("   ❌ Failed")

        print()

    # Show the normalised table
    if results:
        print("=" * 60)
        print("Normalised results (same shape, any vendor):")
        print(f"{'Vendor':<15} {'Interface':<20} {'Admin':<8} {'Oper'}")
        print("-" * 60)
        for r in results:
            print(f"{r.get('vendor','?'):<15} {r.get('interface','?'):<20} "
                  f"{r.get('admin_status','?'):<8} {r.get('oper_status','?')}")

    # ── YOUR TURN ──────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("YOUR TURN:")
    print("  1. Add a Nokia SR-OS or Huawei VRP line to VENDORS and re-run")
    print("  2. Change one vendor's interface to 'down' — does it parse correctly?")
    print("  3. Add a 'description' field to the prompt and see what the model infers")
    print("-" * 60)


if __name__ == "__main__":
    run()
