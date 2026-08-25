#!/usr/bin/env python3
"""
Lab 1 Challenge: JSON Output from the TJU Competition API
Building AI Agents for Network Operations

Learn to get structured JSON output from LLMs.
This is critical for parsing data and building automation.
"""

import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.tju_llm_client import DEFAULT_MODEL, TJUAPIError, generate_text


def get_json_from_tju(prompt: str, model: str = DEFAULT_MODEL) -> Optional[dict]:
    """
    Get structured JSON output from tju-llm.
    
    The key is in the prompt engineering - we explicitly tell the LLM
    to output ONLY valid JSON with no preamble or markdown.
    
    Args:
        prompt: Your instruction (should request JSON format)
        model: Model to use
    
    Returns:
        Parsed JSON dict, or None if parsing fails
    """
    # Wrap the user's prompt with JSON formatting instructions
    json_prompt = f"""You are a JSON-only API. Return ONLY valid JSON with no markdown, no preamble, no explanation.

{prompt}

Output only the JSON:"""
    
    try:
        raw_response = generate_text(
            json_prompt,
            model=model,
            temperature=0.1,
            max_tokens=800,
            timeout=30,
        )
        
        # Try to parse as JSON
        # Remove markdown code fences if present
        if raw_response.startswith("```json"):
            raw_response = raw_response.replace("```json", "").replace("```", "").strip()
        elif raw_response.startswith("```"):
            raw_response = raw_response.replace("```", "").strip()
        
        parsed = json.loads(raw_response)
        return parsed
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}")
        print(f"Raw response: {raw_response[:200]}...")
        return None
    except TJUAPIError as e:
        print(f"❌ Error: {e}")
        return None


# Challenge 1: Parse interface output
def challenge_interface_parser():
    """
    Parse show command output into structured JSON.
    """
    interface_output = """
GigabitEthernet0/1 is up, line protocol is up
  Hardware is iGbE, address is 0000.0c07.ac01
  Internet address is 10.0.0.1/24
  MTU 1500 bytes, BW 1000000 Kbit/sec
    """
    
    prompt = f"""Parse this Cisco interface output into JSON format:

{interface_output}

Return JSON with these fields:
- interface: string
- admin_status: "up" or "down"
- oper_status: "up" or "down"
- ip_address: string or null
- subnet_mask: string or null
- mac_address: string
- mtu: integer
- bandwidth: string

Output only valid JSON."""
    
    print("🔧 Challenge 1: Interface Parser")
    print("="*70)
    
    result = get_json_from_tju(prompt)
    
    if result:
        print("✅ Success! Parsed JSON:")
        print(json.dumps(result, indent=2))
        
        # Validate structure
        required_fields = ["interface", "admin_status", "oper_status", "ip_address"]
        missing = [f for f in required_fields if f not in result]
        
        if missing:
            print(f"\n⚠️  Missing fields: {missing}")
        else:
            print("\n✅ All required fields present!")
    else:
        print("❌ Failed to parse JSON")
    
    return result


# Challenge 2: BGP neighbor status
def challenge_bgp_parser():
    """
    Parse BGP neighbor data into JSON.
    """
    prompt = """Generate JSON for a BGP neighbor summary with 3 neighbors.

Include these fields for each neighbor:
- ip: IPv4 address
- remote_as: AS number
- state: "Established", "Idle", or "Active"
- uptime: string like "3d2h"
- prefixes_received: integer

Output only valid JSON with a 'neighbors' array."""
    
    print("\n🔧 Challenge 2: BGP Neighbor Parser")
    print("="*70)
    
    result = get_json_from_tju(prompt)
    
    if result:
        print("✅ Success! Generated BGP data:")
        print(json.dumps(result, indent=2))
        
        # Validate
        if "neighbors" in result and len(result["neighbors"]) >= 3:
            print(f"\n✅ Generated {len(result['neighbors'])} neighbors")
        else:
            print("\n⚠️  Expected 'neighbors' array with 3+ entries")
    else:
        print("❌ Failed to generate JSON")
    
    return result


# Challenge 3: Multi-vendor support
def challenge_multi_vendor():
    """
    Parse output from different vendors into a common JSON format.
    """
    cisco_output = "GigabitEthernet0/1 is up, line protocol is up"
    arista_output = "Ethernet1 is up, line protocol is up (connected)"
    juniper_output = "ge-0/0/1.0 up up"
    
    print("\n🔧 Challenge 3: Multi-Vendor Parser")
    print("="*70)
    
    for vendor, output in [("Cisco", cisco_output), ("Arista", arista_output), ("Juniper", juniper_output)]:
        prompt = f"""Parse this {vendor} interface status into JSON:

{output}

Return JSON with:
- vendor: string ("{vendor}")
- interface: string
- status: "up" or "down"

Output only valid JSON."""
        
        result = get_json_from_tju(prompt)
        
        if result:
            print(f"\n{vendor}: {json.dumps(result)}")
        else:
            print(f"\n{vendor}: ❌ Failed")


# Challenge 4: Error handling
def challenge_error_handling():
    """
    Demonstrate robust JSON parsing with error recovery.
    """
    print("\n🔧 Challenge 4: Error Handling")
    print("="*70)
    
    # Try to parse invalid data
    prompt = """Parse this malformed interface output:

GigabitEthernet0/1 is flapping rapidly
Error: Unable to determine status

Return JSON with:
- interface: string
- status: "up", "down", or "error"
- error_message: string or null

Output only valid JSON."""
    
    result = get_json_from_tju(prompt)
    
    if result:
        print("✅ Gracefully handled error case:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Failed to handle error case")


if __name__ == "__main__":
    print("🎯 TJU API JSON Challenge - Building AI Agents for Network Operations")
    print("="*70)
    print("\nGoal: Get LLMs to output valid, structured JSON")
    print("="*70)
    
    # Run all challenges
    challenge_interface_parser()
    challenge_bgp_parser()
    challenge_multi_vendor()
    challenge_error_handling()
    
    print("\n" + "="*70)
    print("💡 Key Takeaways:")
    print("  1. Explicitly request JSON-only output (no markdown)")
    print("  2. Use low temperature (0.1-0.3) for consistent structure")
    print("  3. Provide clear field names and types")
    print("  4. Always validate and handle parsing errors")
    print("  5. Strip markdown fences (```json) if present")
    print("="*70)
