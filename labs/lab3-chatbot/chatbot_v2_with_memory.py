#!/usr/bin/env python3
""" Lab 3 Part B: Stateful Chatbot with Memory
Maintains conversation history for multi-turn conversations """
import requests
import json
from typing import List, Dict

class NetworkChatbot:
    """Chatbot with conversation memory for network engineering."""
    def __init__(self, model: str = "llama3.2:3b"):
        self.model = model
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt = """You are a network engineer assistant. Available devices:
- spine1, spine2 (core switches)
- leaf1, leaf2 (access switches)
Provide accurate, concise answers about networking."""

    def chat(self, user_message: str) -> str:
        """Send message with full conversation history."""
        # Add user message to history
        self.conversation_history.append({"role": "user", "content": user_message })
        
        # Build full prompt with history
        full_prompt = self._build_prompt()
        
        # Call Ollama
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 1024
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            assistant_message = data.get("response", "")
            
            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": assistant_message })
            return assistant_message
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to Ollama. Is it running? Try: ollama serve"
        except Exception as e:
            return f"Error: {e}"

    def _build_prompt(self) -> str:
        """Build prompt with system message and conversation history."""
        prompt_parts = [self.system_prompt, "\n\n"]
        for msg in self.conversation_history:
            if msg["role"] == "user":
                prompt_parts.append(f"User: {msg['content']}\n")
            elif msg["role"] == "assistant":
                prompt_parts.append(f"Assistant: {msg['content']}\n")
        prompt_parts.append("Assistant: ")
        return "".join(prompt_parts)

    def reset(self):
        """Clear conversation history."""
        self.conversation_history = []

    def get_history_length(self) -> int:
        """Get number of messages in history."""
        return len(self.conversation_history)

if __name__ == "__main__":
    print("🤖 Stateful Chatbot Demo (Ollama)")
    print("="*70)
    
    bot = NetworkChatbot()
    
    print("\n👤 User: What is OSPF?")
    response1 = bot.chat("What is OSPF?")
    print(f"🤖 Bot: {response1}\n")
    
    print("👤 User: What did I just ask you?")
    response2 = bot.chat("What did I just ask you?")
    print(f"🤖 Bot: {response2}\n")
    
    # Improved check logic
    if response1.startswith("Error:") or response2.startswith("Error:"):
        print("❌ SETUP CHECK FAILED: The bot could not get a valid Ollama response.")
        print("   Please make sure Ollama is running:")
        print("   ollama serve")
        print("   Also make sure the required model is installed:")
        print("   ollama pull llama3.2:3b")
        print(f"   Conversation length: {bot.get_history_length()} messages")
    else:
        print("✅ SUCCESS: The bot remembers!")
        print(f"   Conversation length: {bot.get_history_length()} messages")

    # Interactive mode
    print("\n" + "="*70)
    print("💬 Interactive Mode - Type 'quit' to exit, 'reset' to clear history")
    print("="*70)
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            if user_input.lower() == 'reset':
                bot.reset()
                print("🔄 Conversation history cleared!")
                continue
            if not user_input:
                continue
                
            response = bot.chat(user_input)
            print(f"\n🤖 Bot: {response}")
            print(f"   [{bot.get_history_length()} messages in history]")
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
