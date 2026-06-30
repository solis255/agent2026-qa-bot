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
import re
import requests
from typing import Any, Dict, List, Optional

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

2. get_interface_status(device, interface=None)
   - Get one interface or all interfaces for a device
   - Example: get_interface_status("leaf1", "Ethernet1")
   - Example: get_interface_status("leaf2")

3. get_bgp_summary(device)
   - Get BGP neighbor status
   - Example: get_bgp_summary("spine1")

4. ping_device(target, count=4)
   - Test reachability to a target IP address or hostname
   - Example: ping_device("192.168.0.21", count=4)

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
- 'ping_device' MUST use "target" and may use optional "count". Do not pass "source" or "device". Example: TOOL: ping_device ARGS: {{"target": "192.168.0.21", "count": 4}}.
- 'get_device_status' ONLY takes a "device" argument. NEVER include "interface".
- 'get_interface_status' requires "device"; "interface" is optional. Omit "interface" to get all interfaces for a device.
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
        tool_results: List[Dict[str, Any]] = []

        planned_calls = self._planned_tool_calls(user_message)
        if planned_calls:
            for tool_name, tool_args in planned_calls:
                self._run_tool_call(tool_name, tool_args, seen_calls, tool_results)

            final_response = self._fallback_answer(user_message, tool_results)
            print(f"🤖 Agent: {final_response}\n")
            self.conversation_history.append({
                "role": "assistant",
                "content": final_response
            })
            return final_response

        while iteration < max_iterations:
            iteration += 1

            # Get LLM response
            response = self._call_llm()

            if not response:
                if tool_results:
                    final_response = self._fallback_answer(user_message, tool_results)
                    print(f"🤖 Agent: {final_response}\n")
                    return final_response
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

                self._run_tool_call(tool_name, tool_args, seen_calls, tool_results)
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
        if not final_response:
            final_response = self._fallback_answer(user_message, tool_results)
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
            return self._clean_llm_response(data.get("response", ""))
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to Ollama. Is it running? Try: ollama serve"
        except Exception as e:
            return f"Error: {e}"

    def _clean_llm_response(self, response: str) -> str:
        """Remove reasoning-only text that some local models emit."""
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL | re.IGNORECASE)
        response = response.replace("```text", "").replace("```", "")
        return response.strip()

    def _planned_tool_calls(self, user_message: str) -> List[tuple[str, Dict[str, Any]]]:
        """
        Add deterministic plans for common lab questions.

        Local reasoning models do not always emit well-formed tool calls. These
        plans keep the demo reliable while still feeding real tool output back
        into the final answer step.
        """
        text = user_message.lower()
        devices = ["spine1", "spine2", "leaf1", "leaf2"]

        if "bgp" in text and any(word in text for word in ["all", "network", "sessions", "peers"]):
            return [("get_bgp_summary", {"device": device}) for device in devices]

        mentioned_device = next((device for device in devices if device in text), None)
        if mentioned_device and any(word in text for word in ["status", "health", "state"]):
            return [("get_device_status", {"device": mentioned_device})]

        if mentioned_device and any(word in text for word in ["issue", "issues", "troubleshoot", "problem", "problems"]):
            return [
                ("get_device_status", {"device": mentioned_device}),
                ("get_bgp_summary", {"device": mentioned_device}),
                ("get_interface_status", {"device": mentioned_device}),
            ]

        return []

    def _run_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        seen_calls: set,
        tool_results: List[Dict[str, Any]],
    ) -> None:
        """Execute one tool call, print it, and add it to conversation history."""
        call_key = (tool_name, json.dumps(tool_args, sort_keys=True))
        if call_key in seen_calls:
            return

        seen_calls.add(call_key)
        print(f"🔧 Agent is calling: {tool_name}({json.dumps(tool_args)})")

        try:
            result = self._execute_tool(tool_name, tool_args)
            result_str = json.dumps(result, indent=2)
            print(f"📊 Result:\n{result_str}\n")

            tool_results.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            })
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
            tool_results.append({
                "tool": tool_name,
                "args": tool_args,
                "result": {"error": str(e)},
            })
            self.conversation_history.append({
                "role": "user",
                "content": error_msg
            })

    def _final_answer_from_llm_or_fallback(
        self,
        user_message: str,
        tool_results: List[Dict[str, Any]],
    ) -> str:
        """Ask the LLM for a concise conclusion, then fall back to deterministic facts."""
        self.conversation_history.append({
            "role": "user",
            "content": (
                "Using only the tool results above, provide a concise final answer. "
                "Mention any down BGP peers or down interfaces explicitly."
            )
        })
        final_response = self._call_llm()
        if final_response and not self._parse_tool_call(final_response):
            return final_response
        return self._fallback_answer(user_message, tool_results)

    def _fallback_answer(self, user_message: str, tool_results: List[Dict[str, Any]]) -> str:
        """Build a fact-based answer when the local model gives no usable final text."""
        if not tool_results:
            return "I could not gather enough information to answer."

        text = user_message.lower()
        bgp_results = [item["result"] for item in tool_results if item["tool"] == "get_bgp_summary"]
        interface_results = [item["result"] for item in tool_results if item["tool"] == "get_interface_status"]
        status_results = [item["result"] for item in tool_results if item["tool"] == "get_device_status"]

        if bgp_results and ("bgp" in text or "sessions" in text or "peers" in text):
            total_peers = sum(result.get("total_peers", 0) for result in bgp_results)
            established_peers = sum(result.get("established_peers", 0) for result in bgp_results)
            down_neighbors = []
            for result in bgp_results:
                for neighbor in result.get("neighbors", []):
                    if neighbor.get("state") != "Established":
                        down_neighbors.append(
                            f"{result.get('device')} neighbor {neighbor.get('ip')} is {neighbor.get('state')}"
                        )

            if down_neighbors:
                return (
                    f"No. BGP is not fully healthy: {established_peers}/{total_peers} peers are Established. "
                    + "; ".join(down_neighbors)
                    + "."
                )
            return f"Yes. All BGP sessions are up: {established_peers}/{total_peers} peers are Established."

        if status_results and not bgp_results and not interface_results:
            result = status_results[0]
            if "error" in result:
                return result["error"]
            return (
                f"{result.get('device')} is {result.get('status')} at {result.get('ip')}. "
                f"It is a {result.get('role')} running {result.get('model')} {result.get('version')} "
                f"with uptime {result.get('uptime')}."
            )

        details = []
        for result in status_results:
            if "error" not in result:
                details.append(
                    f"{result.get('device')} is {result.get('status')} "
                    f"({result.get('model')} {result.get('version')}, uptime {result.get('uptime')})"
                )

        for result in bgp_results:
            if "error" not in result:
                total = result.get("total_peers", 0)
                established = result.get("established_peers", 0)
                details.append(f"BGP has {established}/{total} peers Established")
                for neighbor in result.get("neighbors", []):
                    if neighbor.get("state") != "Established":
                        details.append(
                            f"neighbor {neighbor.get('ip')} is {neighbor.get('state')} with {neighbor.get('prefixes')} prefixes"
                        )

        for result in interface_results:
            interfaces = result.get("interfaces")
            if interfaces:
                down_interfaces = [intf for intf in interfaces if intf.get("status") != "up"]
                if down_interfaces:
                    details.extend(
                        f"{intf.get('name')} ({intf.get('description')}) is {intf.get('status')}"
                        for intf in down_interfaces
                    )
                else:
                    details.append("all checked interfaces are up")
            elif result.get("status") != "up":
                details.append(
                    f"{result.get('interface')} ({result.get('description')}) is {result.get('status')}"
                )

        if not details:
            return "The checked device data did not show any obvious issues."

        return ". ".join(details) + "."
    
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
