#!/usr/bin/env python3
"""
Lab 3 Part A: Stateless Chatbot
Shows the problem - no memory between calls
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.tju_llm_client import DEFAULT_MODEL, TJUAPIError, generate_text


def simple_chat(user_message: str, model: str = DEFAULT_MODEL) -> str:
    """Send single message with NO conversation history."""
    try:
        return generate_text(user_message, model=model, temperature=0.7, max_tokens=1024)
    except TJUAPIError as exc:
        return f"Error: {exc}"


if __name__ == "__main__":
    print("🤖 Stateless Chatbot Demo (TJU DeepSeek API)")
    print("="*70)
    
    # First question
    print("\n👤 User: What is OSPF?")
    response1 = simple_chat("What is OSPF?")
    print(f"🤖 Bot: {response1}\n")
    
    # Second question (references first)
    print("👤 User: What did I just ask you?")
    response2 = simple_chat("What did I just ask you?")
    print(f"🤖 Bot: {response2}\n")
    
    print("❌ FAILURE: The bot doesn't remember!")
    print("   Each API call is independent.")
    print("\n💡 Next: See chatbot_v2_with_memory.py for the solution!")
