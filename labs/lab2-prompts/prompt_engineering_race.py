#!/usr/bin/env python3
"""
Lab 2: Prompt Engineering with RACE Framework
Building AI Agents for Network Operations

This lab demonstrates how better prompts produce more consistent,
accurate, and automation-ready JSON output.

Role, Anchors, Context, and
Expected output (RACE) prompt framework.
"""

import json
import re
import requests
from typing import Any, Dict, Optional, Union


# ============================================================================
# JSON Schema
# ============================================================================

INTERFACE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "interface": {"type": "string"},
        "admin_status": {"type": "string", "enum": ["up", "down"]},
        "oper_status": {"type": "string", "enum": ["up", "down"]},
        "ip_address": {"type": ["string", "null"]},
        "prefix_length": {"type": ["integer", "null"]},
        "mac_address": {"type": ["string", "null"]},
        "mtu": {"type": ["integer", "null"]},
    },
    "required": [
        "interface",
        "admin_status",
        "oper_status",
        "ip_address",
        "prefix_length",
        "mac_address",
        "mtu",
    ],
    "additionalProperties": False,
}


# ============================================================================
# Ollama Helper
# ============================================================================

def call_llm(
    prompt: str,
    model: str = "llama3.2:3b",
    temperature: float = 0.0,
    timeout: int = 60,
    response_format: Optional[Union[str, Dict[str, Any]]] = None,
) -> str:
    """
    Call the local Ollama API with a prompt.

    response_format can be:
    - None: normal free-form text output
    - "json": Ollama JSON mode
    - JSON schema dict: stronger structured output
    """

    url = "http://localhost:11434/api/generate"

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }

    # This is the important fix.
    # It tells Ollama to constrain the model output instead of relying only on
    # prompt wording.
    if response_format is not None:
        payload["format"] = response_format

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    except requests.exceptions.ConnectionError:
        return (
            "Error: Could not connect to Ollama. "
            "Make sure Ollama is running with: ollama serve"
        )

    except requests.exceptions.Timeout:
        return "Error: Ollama request timed out."

    except Exception as e:
        return f"Error: {e}"


# ============================================================================
# JSON Helpers
# ============================================================================

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract and parse JSON from an LLM response.

    Handles:
    - Raw JSON
    - JSON wrapped in markdown fences
    - Extra text before or after JSON
    """

    if not text:
        return None

    cleaned = text.strip()

    # Remove markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Try direct JSON parsing first
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # More reliable than a greedy regex.
    # Scan for a JSON object and decode from that point.
    decoder = json.JSONDecoder()

    for index, character in enumerate(cleaned):
        if character != "{":
            continue

        try:
            parsed, _ = decoder.raw_decode(cleaned[index:])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            continue

    return None


def validate_interface_json(data: Dict[str, Any]) -> list[str]:
    """
    Validate that the parsed JSON contains the expected structure.
    """

    errors = []

    required_fields = {
        "interface": str,
        "admin_status": str,
        "oper_status": str,
        "ip_address": (str, type(None)),
        "prefix_length": (int, type(None)),
        "mac_address": (str, type(None)),
        "mtu": (int, type(None)),
    }

    for field, expected_type in required_fields.items():
        if field not in data:
            errors.append(f"Missing field: {field}")
            continue

        if not isinstance(data[field], expected_type):
            errors.append(
                f"Field '{field}' has wrong type. "
                f"Expected {expected_type}, got {type(data[field]).__name__}"
            )

    if data.get("admin_status") not in ["up", "down"]:
        errors.append("admin_status must be 'up' or 'down'")

    if data.get("oper_status") not in ["up", "down"]:
        errors.append("oper_status must be 'up' or 'down'")

    return errors


# ============================================================================
# CHALLENGE 1: Config Parser
# ============================================================================

def bad_config_parser_prompt() -> str:
    """
    BAD PROMPT:
    Vague prompt. No role. No structure. No examples. No constraints.
    """

    return "Parse this config"


def good_config_parser_prompt(config_text: str) -> str:
    """
    GOOD RACE PROMPT:
    Uses the RACE framework to create a structured prompt.

    This version is intentionally strict because smaller local models can
    sometimes drift into writing Python code unless we explicitly forbid it.
    """

    schema_text = json.dumps(INTERFACE_SCHEMA, indent=2)

    return f"""
You are a JSON extraction engine for network automation data.

ROLE:
You extract facts from network interface CLI output so another automation
workflow can consume the result.

ANCHORS:
Read the network interface output and return the extracted values as JSON.
- Return one JSON object only.
- Do not write Python code.
- Do not write a parser function.
- Do not use markdown code fences.
- Do not explain your answer.
- The first character of your answer must be {{.
- The last character of your answer must be }}.
- Use null for missing values.
- Do not invent values that are not present in the input.

JSON SCHEMA:
{schema_text}

CONTEXT:
Example input:
GigabitEthernet0/1 is up, line protocol is up
  Hardware is iGbE, address is 0000.0c07.ac01
  Internet address is 10.0.0.1/24
  MTU 1500 bytes

Expected example output:
{{
  "interface": "GigabitEthernet0/1",
  "admin_status": "up",
  "oper_status": "up",
  "ip_address": "10.0.0.1",
  "prefix_length": 24,
  "mac_address": "0000.0c07.ac01",
  "mtu": 1500
}}

EXPECTED OUTPUT:
NOW PARSE THIS CONFIG:
{config_text}
""".strip()


def test_config_parser() -> None:
    """
    Test the config parser with both bad and good prompts.
    """

    test_config = """
GigabitEthernet0/2 is down, line protocol is down
  Hardware is iGbE, address is 0000.0c07.ac02
  MTU 1500 bytes, BW 1000000 Kbit/sec
""".strip()

    print("\n🧪 Config Parser Test")
    print("=" * 70)

    # ------------------------------------------------------------------------
    # Bad prompt test
    # ------------------------------------------------------------------------

    print("\n❌ BAD PROMPT")
    print("-" * 70)

    bad_prompt = bad_config_parser_prompt()
    print(f"Prompt:\n{bad_prompt}")

    bad_result = call_llm(
        prompt=f"{bad_prompt}\n\n{test_config}",
        temperature=0.7,
    )

    print("\nLLM Result:")
    print(bad_result[:500])

    # ------------------------------------------------------------------------
    # Good prompt test
    # ------------------------------------------------------------------------

    print("\n✅ GOOD PROMPT USING RACE")
    print("-" * 70)

    good_prompt = good_config_parser_prompt(test_config)
    print(f"Prompt length: {len(good_prompt)} characters")

    good_result = call_llm(
        prompt=good_prompt,
        temperature=0.0,
        response_format=INTERFACE_SCHEMA,
    )

    print("\nLLM Result:")
    print(good_result)

    # ------------------------------------------------------------------------
    # Result review
    # ------------------------------------------------------------------------

    print("\n🔎 Result Review")
    print("-" * 70)

    parsed = extract_json(good_result)

    if parsed is None:
        print("❌ Could not parse the LLM response as JSON.")
        print("This prompt may need more refinement.")
        return

    print("✅ Valid JSON detected.")

    errors = validate_interface_json(parsed)

    if errors:
        print("\n⚠️ JSON parsed, but validation found issues:")

        for error in errors:
            print(f"  - {error}")

    else:
        print("✅ JSON passed schema validation.")

    print("\nParsed Structure:")
    print(json.dumps(parsed, indent=2))


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("🎯 RACE Prompt Engineering Workshop")
    print("=" * 70)
    
    print("\nFramework:")
    print("  R - Role")
    print("  A - Anchors")
    print("  C - Context")
    print("  E - Expected output")

    print("\nGoal:")
    print("  Show why vague prompts fail and structured prompts work better")
    print("  for network automation use cases.")
    print("=" * 70)

    test_config_parser()

    print("\n\n💡 Key Takeaways")
    print("=" * 70)
    print("1. BAD: 'Parse this config' creates inconsistent results.")
    print("2. GOOD: RACE prompts give the model Role, Anchors, Context, and Expected output.")
    print("3. Context examples are often more powerful than instructions alone.")
    print("4. Automation needs structured output, not pretty paragraphs or Python code.")
    print("5. Always validate LLM output before using it in a workflow.")
    print("6. Lower temperature plus Ollama structured output gives more predictable results.")
    print("=" * 70)
