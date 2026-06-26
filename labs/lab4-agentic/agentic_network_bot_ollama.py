#!/usr/bin/env python3
"""
Lab 4: Agentic Network Bot (Ollama Version)
AI Networking Workshop - 100% Free, No API Keys Required

This demonstrates building an autonomous AI agent using Ollama that can:
- Query network devices
- Make multi-step decisions
- Troubleshoot autonomously

Uses prompt engineering to achieve tool calling without native API support.
"""

import os
import sys
import json
import requests
from typing import Dict, List, Optional

# Add parent directory to path to import mock devices
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'examples'))

from mock_network_devices import (
    get_device_status,
    get_interface_status,
    get_bgp_summary,
    ping_device,
    execute_command,
    get_topology_info
)


class AgenticNetworkBot:
    """
    An autonomous AI agent using Ollama that can operate network devices.
    
    This implementation uses structured prompts to achieve tool calling
    without requiring paid APIs.
    """
    
    def __init__(self, model: str = "deepseek-r1:8b"):
        """
        Initialize the agentic network bot.
        
        Args:
            model: Ollama model to use (deepseek-r1:8b recommended)
        """
        self.model = model
        self.conversation_history: List[Dict[str, str]] = []
        self.ollama_url = "http://localhost:11434/api/generate"
        
        # Map tool names to Python functions
        self.tools_map = {
            "get_device_status": get_device_status,
            "get_interface_status": get_interface_status,
            "get_bgp_summary": get_bgp_summary,
            "ping_device": ping_device,
            "execute_command": execute_command,
            "get_topology_info": get_topology_info
        }
        
        # Tool descriptions for the AI
        self.tools_description = """
Available Tools:

1. get_device_status(device)
   - Get device info (hostname, version, uptime, role)
   - Example: get_device_status("spine1")

2. get_interface_status(device, interface)
   - Get interface state, IP, MAC
   - Example: get_interface_status("leaf1", "Ethernet1")

3. get_bgp_summary(device)
   - Get BGP neighbor status
   - Example: get_bgp_summary("spine1")

4. ping_device(source, target)
   - Test reachability between devices
   - Example: ping_device("spine1", "192.168.0.21")

5. execute_command(device, command)
   - Execute show commands (read-only)
   - Example: execute_command("leaf1", "show version")

6. get_topology_info()
   - Get full network topology (no arguments)
   - Example: get_topology_info()

Available devices: spine1, spine2, leaf1, leaf2
"""

        self.system_prompt = f"""You are an expert network engineer troubleshooting a data center network.

        {self.tools_description}

CRITICAL RULES FOR ARGUMENTS:
- 'ping_device' MUST have BOTH "source" and "target" arguments (e.g., TOOL: ping_device ARGS: {{"source": "spine1", "target": "192.168.0.21"}}). NEVER pass "device".
- 'get_device_status' ONLY takes a "device" argument. NEVER include "interface".
- 'get_interface_status' MUST have BOTH "device" and "interface" arguments.
- 'execute_command' MUST have BOTH "device" and "command" arguments.

When you need information, output a tool call in this EXACT format:
TOOL: tool_name
ARGS: {{"arg1": "value1", "arg2": "value2"}}

After getting tool results, analyze them and either:
1. Call another tool if you need more info
2. Provide your final answer

Be concise and practical. Focus on solving problems."""

    def chat(self, user_message: str, max_iterations: int = 5) -> str:
        """
        Chat with the agent. It will autonomously call tools as needed.

        Args:
            user_message: The user's question or request
            max_iterations: Maximum tool calls to prevent infinite loops

        Returns:
            The agent's final response
        """
        print(f"\n{'='*70}")
        print(f"👤 User: {user_message}")
        print(f"{'='*70}\n")
        
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        iteration = 0
        seen_calls = set()  # track (tool, args) to prevent duplicate calls

        while iteration < max_iterations:
            iteration += 1

            # Get LLM response
            response = self._call_llm()

            if not response:
                return "Error: Could not get response from Ollama"

            # Check if response contains a tool call
            tool_call = self._parse_tool_call(response)

            if tool_call:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                call_key = (tool_name, json.dumps(tool_args, sort_keys=True))

                # Skip duplicate calls — push the model to conclude instead
                if call_key in seen_calls:
                    self.conversation_history.append({
                        "role": "user",
                        "content": "You already have that result. Please provide your final answer now."
                    })
                    continue

                seen_calls.add(call_key)
                print(f"🔧 Agent is calling: {tool_name}({json.dumps(tool_args)})")

                try:
                    result = self._execute_tool(tool_name, tool_args)
                    result_str = json.dumps(result, indent=2)
                    print(f"📊 Result:\n{result_str}\n")

                    self.conversation_history.append({
                        "role": "assistant",
                        "content": f"TOOL: {tool_name}\nARGS: {json.dumps(tool_args)}"
                    })
                    self.conversation_history.append({
                        "role": "user",
                        "content": f"Tool result:\n{result_str}"
                    })

                except Exception as e:
                    error_msg = f"Tool error: {str(e)}"
                    print(f"❌ {error_msg}\n")
                    self.conversation_history.append({
                        "role": "user",
                        "content": error_msg
                    })
            else:
                # No tool call — final answer
                print(f"🤖 Agent: {response}\n")
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
                return response

        # Max iterations reached — force a summary
        self.conversation_history.append({
            "role": "user",
            "content": "Summarize your findings and give your final answer now."
        })
        final_response = self._call_llm()
        print(f"🤖 Agent: {final_response}\n")
        self.conversation_history.append({
            "role": "assistant",
            "content": final_response
        })
        return final_response
    
    def _call_llm(self) -> str:
        """Call Ollama API with current conversation history."""
        # Build full prompt
        prompt = self._build_prompt()
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Lower for more consistent tool calling
                "num_predict": 500
            }
        }
        
        try:
            response = requests.post(self.ollama_url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to Ollama. Is it running? Try: ollama serve"
        except Exception as e:
            return f"Error: {e}"
    
    def _build_prompt(self) -> str:
        """Build prompt with system message and conversation history."""
        prompt_parts = [self.system_prompt, "\n\n"]
        
        for msg in self.conversation_history:
            if msg["role"] == "user":
                prompt_parts.append(f"User: {msg['content']}\n\n")
            elif msg["role"] == "assistant":
                prompt_parts.append(f"Assistant: {msg['content']}\n\n")
        
        prompt_parts.append("Assistant: ")
        return "".join(prompt_parts)
    
    def _parse_tool_call(self, response: str) -> Optional[Dict]:
        """
        Parse tool call from LLM response.
        
        Expected format:
        TOOL: tool_name
        ARGS: {"arg1": "value1"}
        """
        lines = response.split('\n')
        tool_name = None
        tool_args = {}
        
        for line in lines:
            line = line.strip()
            if line.startswith("TOOL:"):
                tool_name = line.replace("TOOL:", "").strip()
            elif line.startswith("ARGS:"):
                args_str = line.replace("ARGS:", "").strip()
                try:
                    tool_args = json.loads(args_str)
                except json.JSONDecodeError:
                    # Try to extract JSON from the line
                    import re
                    json_match = re.search(r'\{.*\}', args_str)
                    if json_match:
                        try:
                            tool_args = json.loads(json_match.group())
                        except:
                            pass
        
        if tool_name and tool_name in self.tools_map:
            return {"name": tool_name, "args": tool_args}
        
        return None
    
    def _execute_tool(self, tool_name: str, args: Dict) -> Dict:
        """Execute a tool function with given arguments."""
        tool_func = self.tools_map[tool_name]

        # ping_device only accepts 'target' (and optional 'count') — drop 'source'
        if tool_name == "ping_device":
            args = {k: v for k, v in args.items() if k in ("target", "count")}

        # get_topology_info takes no arguments
        if tool_name == "get_topology_info":
            args = {}

        # Call the tool with unpacked arguments
        try:
            result = tool_func(**args)
            return result if isinstance(result, dict) else {"result": str(result)}
        except TypeError as e:
            # Handle argument mismatch
            return {"error": f"Invalid arguments for {tool_name}: {str(e)}"}
    
    def reset(self):
        """Clear conversation history."""
        self.conversation_history = []


def main():
    """Demo the agentic network bot."""
    print("🤖 Agentic Network Bot - Ollama Edition")
    print("="*70)
    print("No API keys required! Using Ollama (deepseek-r1:8b)")
    print("="*70)
    
    # Initialize the bot
    bot = AgenticNetworkBot()
    
    # Test scenarios
    test_queries = [
        "What's the status of spine1?",
        "Are all BGP sessions up?",
        "Check if leaf2 has any issues",
    ]
    
    print("\n🎯 Running test scenarios...\n")
    
    for query in test_queries:
        bot.reset()
        response = bot.chat(query)
        print(f"{'='*70}\n")
    
    # Interactive mode
    print("\n💬 Interactive Mode - Type 'quit' to exit, 'reset' to clear history")
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
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break


if __name__ == "__main__":
    main()