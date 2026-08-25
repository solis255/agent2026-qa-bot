#!/usr/bin/env python3
"""
Lab 1: Simple TJU Competition API Test
Building AI Agents for Network Operations

This script demonstrates basic interaction with the OpenAI-compatible TJU API.
You'll learn how to:
- Make authenticated API calls to tju-llm
- Control generation parameters
- Parse responses
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.tju_llm_client import DEFAULT_MODEL, TJUAPIError, generate_text_result


def chat_with_tju(
    prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 500
) -> dict:
    """
    Send a prompt to the TJU Competition API and get a response.
    
    Args:
        prompt: The question or instruction to send
        model: Competition model name (normally 'tju-llm')
        temperature: Randomness (0.0 = deterministic, 2.0 = very random)
        max_tokens: Maximum length of response
    
    Returns:
        dict with 'response', 'model', 'tokens' keys
    """
    try:
        return generate_text_result(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=30,
        )
    except TJUAPIError as exc:
        print(f"❌ Error: {exc}")
        return {"response": "", "model": model, "tokens": {}}
def compare_models(prompt: str, models: list[str]) -> None:
    """
    Compare the same prompt across different models.
    
    Args:
        prompt: Question to ask
        models: List of model names to test
    """
    print(f"\n{'='*70}")
    print(f"PROMPT: {prompt}")
    print(f"{'='*70}\n")
    
    for model in models:
        print(f"📊 Model: {model}")
        print(f"{'-'*70}")
        
        result = chat_with_tju(prompt, model=model)
        
        if result["response"]:
            print(result["response"])
            print(f"\n💡 Tokens: {result['tokens']['total']} " +
                  f"({result['tokens']['prompt']} prompt + {result['tokens']['response']} response)")
        
        print(f"\n{'='*70}\n")


def demo_temperature_effects(prompt: str, model: str = DEFAULT_MODEL) -> None:
    """
    Demonstrate how temperature affects output randomness.
    
    Args:
        prompt: Question to ask
        model: Which model to use
    """
    temperatures = [0.0, 0.7, 1.5]
    
    print(f"\n{'='*70}")
    print(f"TEMPERATURE COMPARISON: {prompt}")
    print(f"{'='*70}\n")
    
    for temp in temperatures:
        print(f"🌡️  Temperature: {temp}")
        print(f"{'-'*70}")
        
        result = chat_with_tju(prompt, model=model, temperature=temp)
        
        if result["response"]:
            print(result["response"][:300] + "...")  # First 300 chars
        
        print(f"\n{'='*70}\n")


# Example networking prompts
NETWORKING_PROMPTS = [
    "Explain BGP route selection in 3 bullet points",
    "Write a Python function to parse 'show ip interface brief' output",
    "What are the OSPF neighbor states in order?",
    "Generate a basic Cisco router BGP configuration"
]


if __name__ == "__main__":
    print("🤖 TJU Competition API Test - Building AI Agents for Network Operations")
    print("="*70)
    
    # Test 1: Simple chat
    print("\n📝 Test 1: Simple Chat")
    result = chat_with_tju("Explain OSPF in 2 sentences")
    if result["response"]:
        print(f"Response: {result['response']}")
        print(f"Tokens: {result['tokens']['total']}")
    
    # The competition endpoint currently fixes the model to tju-llm.
    
    # Test 3: Temperature effects
    print("\n📝 Test 3: Temperature Effects")
    demo_temperature_effects(
        "Generate a creative name for a network monitoring tool",
        model=DEFAULT_MODEL
    )
    
    # Interactive mode
    print("\n💬 Interactive Mode - Type 'quit' to exit")
    print("="*70)
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break
        
        if not user_input:
            continue
        
        result = chat_with_tju(user_input)
        if result["response"]:
            print(f"\n🤖: {result['response']}")
            print(f"   [{result['tokens']['total']} tokens]")
