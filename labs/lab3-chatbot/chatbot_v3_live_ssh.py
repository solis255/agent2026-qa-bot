#!/usr/bin/env python3
"""
Lab 3 Part C: Stateful Chatbot with Live SSH Context
Building AI Agents for Network Operations

LAB MODE:  USE_MOCK = True  (works without any devices)
AFTER THE LAB:  Set USE_MOCK = False and update DEVICE_CONFIG

What this adds on top of chatbot_v2_with_memory.py:
- A LiveDeviceContext class that fetches real device state via Netmiko SSH
- The chatbot's system prompt is populated with live (or mock) device data
  at startup, so it can answer questions about current network state
- Commands: 'refresh' re-fetches device data mid-conversation
"""

import requests
import json
from typing import List, Dict

# ============================================================================
# TOGGLE: Mock data vs live SSH
# ============================================================================

USE_MOCK = True  # Flip to False with real devices after the lab

DEVICE_CONFIG = {
    "spine1": {"device_type": "arista_eos", "host": "192.168.0.11", "username": "admin", "password": "admin", "port": 22},
    "spine2": {"device_type": "arista_eos", "host": "192.168.0.12", "username": "admin", "password": "admin", "port": 22},
    "leaf1":  {"device_type": "arista_eos", "host": "192.168.0.21", "username": "admin", "password": "admin", "port": 22},
    "leaf2":  {"device_type": "arista_eos", "host": "192.168.0.22", "username": "admin", "password": "admin", "port": 22},
}

# ============================================================================
# MOCK DATA
# ============================================================================

_MOCK_INT_BRIEF = {
    "spine1": (
        "Ethernet1  unassigned  up    up\n"
        "Ethernet2  unassigned  up    up\n"
        "Ethernet3  unassigned  up    up\n"
        "Loopback0  10.0.0.11   up    up\n"
        "Mgmt1      192.168.0.11 up   up"
    ),
    "spine2": (
        "Ethernet1  unassigned  up    up\n"
        "Ethernet2  unassigned  up    up\n"
        "Ethernet3  unassigned  up    up\n"
        "Loopback0  10.0.0.12   up    up\n"
        "Mgmt1      192.168.0.12 up   up"
    ),
    "leaf1": (
        "Ethernet1  unassigned  up    up\n"
        "Ethernet2  unassigned  up    up\n"
        "Ethernet3  unassigned  down  down\n"
        "Loopback0  10.0.1.21   up    up\n"
        "Mgmt1      192.168.0.21 up   up"
    ),
    "leaf2": (
        "Ethernet1  unassigned  up    up\n"
        "Ethernet2  unassigned  up    up\n"
        "Ethernet3  unassigned  down  down\n"
        "Loopback0  10.0.1.22   up    up\n"
        "Mgmt1      192.168.0.22 up   up"
    ),
}

_MOCK_BGP = {
    "spine1": "10.1.1.1 65011 Estab 3d02h  150\n10.1.1.3 65012 Estab 3d02h  200",
    "spine2": "10.1.2.1 65011 Estab 5d01h  150\n10.1.2.3 65012 Estab 5d01h  200",
    "leaf1":  "10.1.1.0 65001 Estab 3d01h  50\n10.1.2.0 65001 Estab 3d01h  50",
    "leaf2":  "10.1.1.2 65001 Estab 2d03h  50\n10.1.2.2 65001 Idle  0:00   0",
}


# ============================================================================
# LIVE DEVICE CONTEXT — fetches real state and builds a snapshot string
# ============================================================================

class LiveDeviceContext:
    """
    Collects device state via SSH (or mock) and produces a text snapshot
    suitable for embedding in a chatbot system prompt.
    """

    def __init__(self, devices: List[str] = None):
        self.devices = devices or list(DEVICE_CONFIG.keys())
        self.snapshot: str = ""
        self.refresh()

    def refresh(self):
        """(Re-)fetch device state and rebuild the snapshot."""
        mode = "mock" if USE_MOCK else "SSH"
        print(f"  Collecting device state [{mode}]...")
        sections = []
        for device in self.devices:
            intf = self._fetch(device, "show ip interface brief")
            bgp  = self._fetch(device, "show bgp summary")
            sections.append(
                f"--- {device} ---\n"
                f"Interfaces:\n{intf}\n"
                f"BGP neighbors:\n{bgp}"
            )
        self.snapshot = "\n\n".join(sections)
        print(f"  Snapshot ready ({len(self.snapshot)} chars)\n")

    def _fetch(self, device: str, command: str) -> str:
        if USE_MOCK:
            return self._mock(device, command)

        try:
            from netmiko import ConnectHandler
        except ImportError:
            print("  netmiko not installed — pip install -r requirements.txt")
            return self._mock(device, command)

        cfg = DEVICE_CONFIG.get(device)
        if not cfg:
            return f"Error: {device} not in DEVICE_CONFIG"
        try:
            with ConnectHandler(**cfg) as conn:
                return conn.send_command(command)
        except Exception as exc:
            print(f"  SSH error ({device}): {exc}  — using mock")
            return self._mock(device, command)

    def _mock(self, device: str, command: str) -> str:
        dev = device.lower()
        if "interface" in command.lower():
            return _MOCK_INT_BRIEF.get(dev, f"[mock] no data for {dev}")
        if "bgp" in command.lower():
            return _MOCK_BGP.get(dev, f"[mock] no data for {dev}")
        return f"[mock] command '{command}' not mocked"


# ============================================================================
# CHATBOT
# ============================================================================

class LiveNetworkChatbot:
    """
    Stateful chatbot with real (or mock) device context injected at startup.
    Supports 'refresh' to re-fetch device state mid-conversation.
    """

    def __init__(self, model: str = "llama3.2:3b"):
        self.model = model
        self.conversation_history: List[Dict[str, str]] = []
        self.context = LiveDeviceContext()
        self._build_system_prompt()

    def _build_system_prompt(self):
        mode = "live SSH data" if not USE_MOCK else "mock data (USE_MOCK=True)"
        self.system_prompt = f"""You are a network engineer assistant with access to real-time device state ({mode}).

CURRENT NETWORK STATE:
{self.context.snapshot}

Topology: spine1, spine2 (core), leaf1, leaf2 (access).
BGP underlay AS numbers: spines=65001, leaf1=65011, leaf2=65012.

When answering questions, reference the device state above.
Be concise and accurate."""

    def refresh_context(self):
        """Re-fetch device state and rebuild system prompt."""
        self.context.refresh()
        self._build_system_prompt()
        print("Context refreshed — chatbot now has up-to-date device state.")

    def chat(self, user_message: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_message})
        prompt = self._build_prompt()

        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.5, "num_predict": 1024},
                },
                timeout=60,
            )
            resp.raise_for_status()
            assistant_msg = resp.json().get("response", "").strip()
            self.conversation_history.append({"role": "assistant", "content": assistant_msg})
            return assistant_msg
        except requests.exceptions.ConnectionError:
            return "Error: Ollama not running — try: ollama serve"
        except Exception as exc:
            return f"Error: {exc}"

    def _build_prompt(self) -> str:
        parts = [self.system_prompt, "\n\n"]
        for msg in self.conversation_history:
            prefix = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{prefix}: {msg['content']}\n")
        parts.append("Assistant: ")
        return "".join(parts)

    def reset(self):
        self.conversation_history = []

    def get_history_length(self) -> int:
        return len(self.conversation_history)


# ============================================================================
# DEMO
# ============================================================================

if __name__ == "__main__":
    mode = "MOCK DATA (no real devices needed)" if USE_MOCK else "LIVE SSH — real devices"
    print("🤖 Live SSH Chatbot  |  Building AI Agents for Network Operations")
    print("=" * 70)
    print(f"Mode: {mode}")
    print("To use real devices: set USE_MOCK = False and update DEVICE_CONFIG")
    print("=" * 70)

    print("\nInitializing chatbot (fetching device state)...")
    bot = LiveNetworkChatbot()

    # Scripted demo — shows the chatbot can answer from device context
    demo_questions = [
        "Which interfaces are currently down?",
        "Are all BGP sessions healthy? Any sessions that are Idle?",
        "What did I just ask you about?",  # Tests memory
    ]

    print("Running demo questions...\n")
    for q in demo_questions:
        print(f"👤 {q}")
        answer = bot.chat(q)
        print(f"🤖 {answer}\n")

    # Interactive mode
    print("=" * 70)
    print("💬 Interactive Mode")
    print("Commands: 'quit' to exit | 'reset' to clear history | 'refresh' to re-fetch device state")
    print("=" * 70)

    while True:
        try:
            user_input = input("\n👤 You: ").strip()

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("👋 Goodbye!")
                break
            if user_input.lower() == "reset":
                bot.reset()
                print("🔄 History cleared.")
                continue
            if user_input.lower() == "refresh":
                bot.refresh_context()
                continue

            response = bot.chat(user_input)
            print(f"\n🤖 {response}")
            print(f"   [{bot.get_history_length()} messages in history]")

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
