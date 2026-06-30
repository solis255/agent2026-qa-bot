#!/usr/bin/env python3
"""
Lab 1: Simple Ollama Test
Building AI Agents for Network Operations

This script demonstrates basic interaction with Ollama's API.
You'll learn how to:
- Make API calls to local LLMs
- Control generation parameters
- Parse responses
"""

import requests
import json
from typing import Optional


def chat_with_ollama(
    prompt: str,
    model: str = "llama3.2:3b",
    temperature: float = 0.7,
    max_tokens: int = 500
) -> dict:
    """
    Send a prompt to Ollama and get a response.
    
    Args:
        prompt: The question or instruction to send
        model: Model name (e.g., 'llama3.2:3b', 'llama3.1:8b')
        temperature: Randomness (0.0 = deterministic, 2.0 = very random)
        max_tokens: Maximum length of response
    
    Returns:
        dict with 'response', 'model', 'tokens' keys
    """
    url = "http://localhost:11434/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        return {
            "response": data.get("response", ""),
            "model": data.get("model", model),
            "tokens": {
                "prompt": data.get("prompt_eval_count", 0),
                "response": data.get("eval_count", 0),
                "total": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            }
        }
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to Ollama. Is it running?")
        print("   Try: ollama serve")
        return {"response": "", "model": model, "tokens": {}}
    except Exception as e:
        print(f"❌ Error: {e}")
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
        
        result = chat_with_ollama(prompt, model=model)
        
        if result["response"]:
            print(result["response"])
            print(f"\n💡 Tokens: {result['tokens']['total']} " +
                  f"({result['tokens']['prompt']} prompt + {result['tokens']['response']} response)")
        
        print(f"\n{'='*70}\n")


def demo_temperature_effects(prompt: str, model: str = "llama3.2:3b") -> None:
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
        
        result = chat_with_ollama(prompt, model=model, temperature=temp)
        
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
    print("🤖 Ollama API Test - Building AI Agents for Network Operations")
    print("="*70)
    
    # Test 1: Simple chat
    print("\n📝 Test 1: Simple Chat")
    result = chat_with_ollama("Explain OSPF in 2 sentences")
    if result["response"]:
        print(f"Response: {result['response']}")
        print(f"Tokens: {result['tokens']['total']}")
    
    # Test 2: Compare models (uncomment if you have both models)
    # print("\n📝 Test 2: Model Comparison")
    # compare_models(
    #     "Explain BGP route selection in 3 bullet points",
    #     ["llama3.2:3b", "llama3.1:8b"]
    # )
    
    # Test 3: Temperature effects
    print("\n📝 Test 3: Temperature Effects")
    demo_temperature_effects(
        "Generate a creative name for a network monitoring tool",
        model="llama3.2:3b"
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
        
        result = chat_with_ollama(user_input)
        if result["response"]:
            print(f"\n🤖: {result['response']}")
            print(f"   [{result['tokens']['total']} tokens]")
