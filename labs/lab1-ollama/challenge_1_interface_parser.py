#!/usr/bin/env python3
"""
Lab 1 — Challenge 1: Parse Interface Output to JSON
Building AI Agents for Network Operations

GOAL:
    Get Ollama to read raw Cisco 'show interface' output and
    return it as structured JSON your code can work with.

WHY THIS MATTERS:
    Network devices return unstructured text. To automate anything
    you need to convert that text into data. LLMs can do this
    without brittle regex parsers.

RUN:
    python challenge_1_interface_parser.py
"""

import requests
import json


# ── Helper ────────────────────────────────────────────────────────────────

def ask_ollama(prompt: str, model: str = "llama3.2:3b") -> dict | None:
    """
    Send a prompt to Ollama and try to parse the response as JSON.

    Returns a dict on success, or None if the response isn't valid JSON.
    """
    # Wrap the prompt so the model knows to return ONLY JSON
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
                "options": {"temperature": 0.1},  # low temp = consistent output
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

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
    except Exception as e:
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
    print("Asking Ollama to parse it...\n")

    result = ask_ollama(PROMPT)

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
