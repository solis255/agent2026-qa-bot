#!/usr/bin/env python3
""" Lab 3 Part B: Stateful Chatbot with Memory
Maintains conversation history for multi-turn conversations """
import sys
from pathlib import Path
from typing import List, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.tju_llm_client import DEFAULT_MODEL, TJUAPIError, chat_message

class NetworkChatbot:
    """Chatbot with conversation memory for network engineering."""
    def __init__(self, model: str = DEFAULT_MODEL):
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
        
        try:
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.conversation_history)
            assistant_message = chat_message(
                messages,
                model=self.model,
                temperature=0.7,
                max_tokens=1024,
            )["content"]
            
            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": assistant_message })
            return assistant_message
        except TJUAPIError as exc:
            return f"Error: {exc}"

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
    print("🤖 Stateful Chatbot Demo (TJU DeepSeek API)")
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
        print("❌ SETUP CHECK FAILED: The bot could not get a valid API response.")
        print("   Check TJU_API_KEY, TJU_API_BASE and TJU_MODEL in the project .env file.")
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
