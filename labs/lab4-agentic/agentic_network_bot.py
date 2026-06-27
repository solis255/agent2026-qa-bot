#!/usr/bin/env python3
"""
Lab 4: Agentic Network Bot
AI Networking Workshop - 100% Free, No API Keys Required

This lab demonstrates how to build an AI agent that can autonomously
query and operate network devices using tool calling.

Uses Ollama (deepseek-r1:8b) with native tool calling — no paid API needed.

The agent can:
- Check device status
- Query BGP neighbors
- Check interface status
- Execute show commands
- Make multi-step decisions autonomously
"""

import json
import requests
from typing import Dict, List, Optional

# Import our mock network devices
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'examples'))

from mock_network_devices import (
    get_device_status,
    get_interface_status,
    get_bgp_summary,
    ping_device,
    execute_command,
    get_topology_info,
    MockNetworkDevice
)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "deepseek-r1:8b"


class AgenticNetworkBot:
    """
    An AI agent that can autonomously operate network devices.

    Features:
    - Autonomous decision making
    - Multi-step problem solving
    - Native tool calling via Ollama
    - Conversation memory
    """

    def __init__(self, model: str = MODEL):
        self.model = model
        self.conversation_history: List[Dict] = []

        # Map tool names to Python functions
        self.tools_map = {
            "get_device_status": get_device_status,
            "get_interface_status": get_interface_status,
            "get_bgp_summary": get_bgp_summary,
            "ping_device": ping_device,
            "execute_command": execute_command,
            "get_topology_info": get_topology_info,
        }

        # Ollama/OpenAI-compatible tool schemas
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_device_status",
                    "description": "Get operational status of a network device (version, uptime, role)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device hostname (spine1, spine2, leaf1, or leaf2)",
                            }
                        },
                        "required": ["device"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_interface_status",
                    "description": "Get status of network interfaces on a device",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {"type": "string", "description": "Device hostname"},
                            "interface": {
                                "type": "string",
                                "description": "Specific interface name (optional, returns all if not specified)",
                            },
                        },
                        "required": ["device"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_bgp_summary",
                    "description": "Get BGP neighbor summary from a device",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {"type": "string", "description": "Device hostname"}
                        },
                        "required": ["device"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "ping_device",
                    "description": "Ping a network device to check reachability",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "Device hostname or IP address",
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of ping packets (default 4)",
                                "default": 4,
                            },
                        },
                        "required": ["target"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Execute a show command on a device (read-only, show commands only)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {"type": "string", "description": "Device hostname"},
                            "command": {
                                "type": "string",
                                "description": "Show command to execute (e.g., 'show version')",
                            },
                        },
                        "required": ["device", "command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_topology_info",
                    "description": "Get information about the network topology structure",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

        self.system_prompt = """You are an expert network engineer assistant working with a spine-leaf Arista cEOS network topology.

Available devices in the lab:
- spine1 (192.168.0.11) - Core spine switch
- spine2 (192.168.0.12) - Core spine switch
- leaf1 (192.168.0.21) - Leaf/access switch
- leaf2 (192.168.0.22) - Leaf/access switch

Network design:
- 2-spine, 2-leaf topology
- BGP underlay (eBGP between tiers)
- Each leaf connects to both spines

When troubleshooting:
1. Gather information systematically
2. Check multiple devices if needed
3. Correlate data across the topology
4. Provide clear, actionable insights

Be concise and technical. Focus on facts from device output."""

    # ------------------------------------------------------------------
    # Core chat loop
    # ------------------------------------------------------------------

    def chat(self, user_message: str, verbose: bool = True, max_iterations: int = 10) -> str:
        """
        Send a message and let the agent autonomously solve the problem.

        Args:
            user_message:   The user's question or instruction
            verbose:        Print tool calls as they happen
            max_iterations: Safety cap on tool-call rounds

        Returns:
            Agent's final text response
        """
        self.conversation_history.append({"role": "user", "content": user_message})

        for _ in range(max_iterations):
            response_msg = self._call_ollama()

            tool_calls = response_msg.get("tool_calls") or []

            if not tool_calls:
                # No tool calls → final answer
                final_text = response_msg.get("content", "").strip()
                self.conversation_history.append({"role": "assistant", "content": final_text})
                return final_text

            # Record the assistant turn (with tool_calls)
            self.conversation_history.append(response_msg)

            # Execute each tool and feed results back
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", {})
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                if verbose:
                    print(f"\n🔧 Agent calling: {tool_name}({json.dumps(tool_args)})")

                result = self._execute_tool(tool_name, tool_args)

                if verbose:
                    print(f"📊 Result: {json.dumps(result, indent=2)}")

                self.conversation_history.append({
                    "role": "tool",
                    "content": json.dumps(result),
                })

        # Fallback if we hit the iteration cap
        return self._call_ollama().get("content", "Max iterations reached.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call_ollama(self) -> Dict:
        """POST to Ollama /api/chat and return the message dict."""
        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation_history

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": self.tools,
            "stream": False,
            "options": {"temperature": 0.3},
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json().get("message", {"role": "assistant", "content": "No response"})
        except requests.exceptions.ConnectionError:
            return {"role": "assistant", "content": "Error: Cannot connect to Ollama. Is it running? Try: ollama serve"}
        except Exception as exc:
            return {"role": "assistant", "content": f"Error: {exc}"}

    def _execute_tool(self, tool_name: str, args: Dict) -> Dict:
        """Call the matching Python function and return a result dict."""
        tool_func = self.tools_map.get(tool_name)
        if not tool_func:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            result = tool_func(**args)
            return result if isinstance(result, dict) else {"result": str(result)}
        except TypeError as exc:
            return {"error": f"Invalid arguments for {tool_name}: {exc}"}

    def reset(self):
        """Clear conversation history."""
        self.conversation_history = []


# =============================================================================
# DEMO & TEST SCENARIOS
# =============================================================================

def demo_simple_query():
    print("\n" + "="*70)
    print("DEMO 1: Simple Device Query")
    print("="*70)
    bot = AgenticNetworkBot()
    response = bot.chat("What's the status of spine1?")
    print(f"\n🤖 Agent: {response}")


def demo_multi_device_query():
    print("\n" + "="*70)
    print("DEMO 2: Multi-Device Query (Autonomous)")
    print("="*70)
    bot = AgenticNetworkBot()
    response = bot.chat("Are all BGP sessions up in the network?")
    print(f"\n🤖 Agent: {response}")


def demo_troubleshooting():
    print("\n" + "="*70)
    print("DEMO 3: Troubleshooting (Multi-Step Reasoning)")
    print("="*70)
    bot = AgenticNetworkBot()
    response = bot.chat(
        "I notice leaf2 has an interface down. "
        "Can you investigate and tell me which interface and what it connects to?"
    )
    print(f"\n🤖 Agent: {response}")


def demo_topology_analysis():
    print("\n" + "="*70)
    print("DEMO 4: Topology Analysis")
    print("="*70)
    bot = AgenticNetworkBot()
    response = bot.chat("Which device has the most BGP peers and why?")
    print(f"\n🤖 Agent: {response}")


def interactive_mode():
    print("\n" + "="*70)
    print("🤖 Interactive Agentic Network Bot  (Ollama / deepseek-r1:8b)")
    print("="*70)
    print("Available devices: spine1, spine2, leaf1, leaf2")
    print("Type 'quit' to exit, 'reset' to clear history\n")
    print("="*70)

    bot = AgenticNetworkBot()
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["quit", "exit", "q"]:
                print("👋 Goodbye!")
                break
            if user_input.lower() == "reset":
                bot.reset()
                print("🔄 Conversation reset")
                continue
            print()
            response = bot.chat(user_input, verbose=True)
            print(f"\n🤖 Agent: {response}")
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break


# =============================================================================
# CHALLENGES
# =============================================================================

def challenge_1():
    """Challenge 1: Device Inventory — agent should call get_device_status() for all 4 devices"""
    print("\n" + "="*70)
    print("CHALLENGE 1: Device Inventory Report")
    print("="*70)
    bot = AgenticNetworkBot()
    response = bot.chat(
        "Create a device inventory report for all devices in the topology. "
        "Include hostname, role, software version, and uptime."
    )
    print(f"\n🤖 Agent: {response}")


def challenge_2():
    """Challenge 2: BGP Health Check — agent should check all devices and correlate"""
    print("\n" + "="*70)
    print("CHALLENGE 2: BGP Health Check")
    print("="*70)
    bot = AgenticNetworkBot()
    response = bot.chat(
        "Perform a complete BGP health check. Tell me if any sessions are down "
        "and which devices are affected."
    )
    print(f"\n🤖 Agent: {response}")


def challenge_3():
    """Challenge 3: Find the Problem — agent should find leaf2 Ethernet3 down"""
    print("\n" + "="*70)
    print("CHALLENGE 3: Find the Problem")
    print("="*70)
    bot = AgenticNetworkBot()
    response = bot.chat(
        "Something is wrong with one of the devices. "
        "Can you investigate and tell me what the issue is?"
    )
    print(f"\n🤖 Agent: {response}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("\n🎯 Lab 4: Agentic Network Bot  (Ollama / deepseek-r1:8b)")
    print("="*70)
    print("No API keys required! Uses Ollama running locally.")
    print("Make sure Ollama is running:  ollama serve")
    print("Make sure model is pulled:    ollama pull deepseek-r1:8b")
    print("="*70)

    demo_simple_query()
    # demo_multi_device_query()
    # demo_troubleshooting()
    # demo_topology_analysis()

    # Or run interactive mode:
    # interactive_mode()

    # Or try the challenges:
    # challenge_1()
    # challenge_2()
    # challenge_3()

    print("\n" + "="*70)
    print("✅ Lab 4 Complete!")
    print("="*70)
    print("\n💡 Key Takeaways:")
    print("  1. Agents autonomously decide which tools to call")
    print("  2. Multi-step reasoning enables complex troubleshooting")
    print("  3. Tool calling connects LLMs to real infrastructure")
    print("  4. Same code works with real devices (just change the tool functions)")
    print("="*70)
