#!/usr/bin/env python3
"""
Lab 4B: Agentic Network Bot with Real SSH using Netmiko
AI Networking Workshop - Local Ollama + Real Network Device SSH

WARNING:
- This version connects to real network devices over SSH.
- The agent is intentionally limited to read-only commands.
- The generic execute_command tool only allows commands that start with "show".
- Dangerous commands such as configure, reload, delete, copy, write, erase, etc. are blocked.

Requirements:
    pip install -r requirements.txt

Ollama:
    ollama serve
    ollama pull deepseek-r1:8b

Optional environment variables:
    export NETMIKO_USERNAME="admin"
    export NETMIKO_PASSWORD="your-password"
    export NETMIKO_SECRET="enable-secret-if-needed"
    export NETMIKO_DEVICE_TYPE="arista_eos"

Per-device overrides are also supported:
    export SPINE1_HOST="192.168.0.11"
    export SPINE2_HOST="192.168.0.12"
    export LEAF1_HOST="192.168.0.21"
    export LEAF2_HOST="192.168.0.22"
"""

import getpass
import ipaddress
import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

try:
    from netmiko import ConnectHandler
    from netmiko.exceptions import NetMikoAuthenticationException, NetMikoTimeoutException
except ImportError as exc:
    raise SystemExit(
        "Netmiko is not installed. Install it with: pip install -r requirements.txt"
    ) from exc


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
DEFAULT_DEVICE_TYPE = os.getenv("NETMIKO_DEVICE_TYPE", "arista_eos")
DEFAULT_PORT = int(os.getenv("NETMIKO_PORT", "22"))


# -----------------------------------------------------------------------------
# Device inventory
# -----------------------------------------------------------------------------
# Update these values for your lab.
# device_type examples:
#   Arista EOS:      arista_eos
#   Cisco IOS/XE:    cisco_ios or cisco_xe
#   Cisco NX-OS:     cisco_nxos
#   Juniper Junos:   juniper_junos

LAB_DEVICES: Dict[str, Dict[str, Any]] = {
    "spine1": {
        "host": os.getenv("SPINE1_HOST", "192.168.0.11"),
        "device_type": os.getenv("SPINE1_DEVICE_TYPE", DEFAULT_DEVICE_TYPE),
        "port": int(os.getenv("SPINE1_PORT", str(DEFAULT_PORT))),
        "role": "Core spine switch",
    },
    "spine2": {
        "host": os.getenv("SPINE2_HOST", "192.168.0.12"),
        "device_type": os.getenv("SPINE2_DEVICE_TYPE", DEFAULT_DEVICE_TYPE),
        "port": int(os.getenv("SPINE2_PORT", str(DEFAULT_PORT))),
        "role": "Core spine switch",
    },
    "leaf1": {
        "host": os.getenv("LEAF1_HOST", "192.168.0.21"),
        "device_type": os.getenv("LEAF1_DEVICE_TYPE", DEFAULT_DEVICE_TYPE),
        "port": int(os.getenv("LEAF1_PORT", str(DEFAULT_PORT))),
        "role": "Leaf/access switch",
    },
    "leaf2": {
        "host": os.getenv("LEAF2_HOST", "192.168.0.22"),
        "device_type": os.getenv("LEAF2_DEVICE_TYPE", DEFAULT_DEVICE_TYPE),
        "port": int(os.getenv("LEAF2_PORT", str(DEFAULT_PORT))),
        "role": "Leaf/access switch",
    },
}

LAB_TOPOLOGY = {
    "design": "2-spine, 2-leaf topology with BGP underlay",
    "connections": {
        "leaf1": ["spine1", "spine2"],
        "leaf2": ["spine1", "spine2"],
        "spine1": ["leaf1", "leaf2"],
        "spine2": ["leaf1", "leaf2"],
    },
}


# -----------------------------------------------------------------------------
# Safety helpers
# -----------------------------------------------------------------------------

BLOCKED_COMMAND_WORDS = [
    "configure",
    "conf t",
    "copy",
    "delete",
    "erase",
    "format",
    "reload",
    "reboot",
    "write",
    "wr mem",
    "commit",
    "replace",
    "install",
    "bash",
    "sudo",
    "python",
    "tclsh",
    "guestshell",
]

# Commands that can reveal secrets or generate very large output.
BLOCKED_SHOW_PATTERNS = [
    "show running-config",
    "show startup-config",
    "show tech",
    "show tech-support",
]

VALID_DEVICE_NAME = re.compile(r"^[a-zA-Z0-9_.-]+$")
VALID_INTERFACE_NAME = re.compile(r"^[a-zA-Z0-9_./:-]+$")
VALID_TARGET = re.compile(r"^[a-zA-Z0-9_.:-]+$")


def normalize_command(command: str) -> str:
    """Normalize whitespace for safer command validation."""
    return " ".join(command.strip().split())


def is_safe_show_command(command: str) -> bool:
    """Allow only read-only show commands and block risky variants."""
    normalized = normalize_command(command).lower()

    if not normalized.startswith("show "):
        return False

    for blocked in BLOCKED_COMMAND_WORDS:
        if blocked in normalized:
            return False

    for blocked in BLOCKED_SHOW_PATTERNS:
        if normalized.startswith(blocked):
            return False

    # Avoid command chaining or unexpected shell-like behavior.
    if any(token in normalized for token in [";", "&&", "||", "`", "$("]):
        return False

    return True


def resolve_target(target: str) -> str:
    """Resolve a device name to its management IP/host, or validate a direct target."""
    clean_target = target.strip()
    if clean_target in LAB_DEVICES:
        return str(LAB_DEVICES[clean_target]["host"])

    if not VALID_TARGET.match(clean_target):
        raise ValueError(f"Invalid target: {target}")

    # Accept IPs and DNS-style names.
    try:
        ipaddress.ip_address(clean_target)
        return clean_target
    except ValueError:
        return clean_target


# -----------------------------------------------------------------------------
# Agent
# -----------------------------------------------------------------------------


class AgenticNetworkBot:
    """
    An AI agent that can autonomously query real network devices using SSH.

    Features:
    - Ollama local LLM
    - Netmiko SSH tool functions
    - Read-only safety guardrails
    - Conversation memory
    - Multi-step troubleshooting
    """

    def __init__(
        self,
        model: str = MODEL,
        username: Optional[str] = None,
        password: Optional[str] = None,
        secret: Optional[str] = None,
    ):
        self.model = model
        self.username = username or os.getenv("NETMIKO_USERNAME") or input("SSH username: ")
        self.password = password or os.getenv("NETMIKO_PASSWORD") or getpass.getpass("SSH password: ")
        self.secret = secret if secret is not None else os.getenv("NETMIKO_SECRET", "")
        self.conversation_history: List[Dict[str, Any]] = []

        # Map tool names to Python methods.
        self.tools_map = {
            "get_device_status": self.get_device_status,
            "get_interface_status": self.get_interface_status,
            "get_bgp_summary": self.get_bgp_summary,
            "ping_device": self.ping_device,
            "execute_command": self.execute_command,
            "get_topology_info": self.get_topology_info,
        }

        # Ollama/OpenAI-compatible tool schemas.
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_device_status",
                    "description": "SSH to a device and collect basic operational status such as hostname and version.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {
                                "type": "string",
                                "description": "Device hostname: spine1, spine2, leaf1, or leaf2",
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
                    "description": "SSH to a device and collect interface status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {"type": "string", "description": "Device hostname"},
                            "interface": {
                                "type": "string",
                                "description": "Optional interface name. If omitted, returns interface status summary.",
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
                    "description": "SSH to a device and collect BGP neighbor summary.",
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
                    "description": "Check whether a lab device is reachable by opening an SSH session. This is an SSH reachability check, not an ICMP ping.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "Device hostname or management IP address",
                            },
                            "count": {
                                "type": "integer",
                                "description": "Unused compatibility field from the mock lab. Kept so old prompts still work.",
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
                    "description": "Execute a read-only show command on a device over SSH. Only commands beginning with 'show' are allowed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device": {"type": "string", "description": "Device hostname"},
                            "command": {
                                "type": "string",
                                "description": "Read-only show command, for example 'show version' or 'show ip bgp summary'.",
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
                    "description": "Get static lab topology information.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

        self.system_prompt = """You are an expert network engineer assistant working with a spine-leaf network topology.

Available devices in the lab:
- spine1 - Core spine switch
- spine2 - Core spine switch
- leaf1 - Leaf/access switch
- leaf2 - Leaf/access switch

Network design:
- 2-spine, 2-leaf topology
- BGP underlay, usually eBGP between tiers
- Each leaf connects to both spines

Safety rules:
- You may only use the provided tools.
- Do not attempt configuration changes.
- Use execute_command only for read-only show commands.
- Never request reload, delete, erase, configure, copy, write, or commit actions.

When troubleshooting:
1. Gather information systematically.
2. Check multiple devices if needed.
3. Correlate data across the topology.
4. Provide clear, actionable insights.

Be concise and technical. Focus on facts from device output."""

    # ------------------------------------------------------------------
    # Netmiko-backed tool functions
    # ------------------------------------------------------------------

    def _device_params(self, device: str) -> Dict[str, Any]:
        """Build the Netmiko connection dictionary for a device."""
        if device not in LAB_DEVICES:
            raise ValueError(f"Unknown device '{device}'. Valid devices: {', '.join(LAB_DEVICES)}")

        device_info = LAB_DEVICES[device]
        return {
            "device_type": device_info["device_type"],
            "host": device_info["host"],
            "port": device_info.get("port", 22),
            "username": self.username,
            "password": self.password,
            "secret": self.secret,
            "fast_cli": False,
        }

    def _send_show_command(self, device: str, command: str, read_timeout: int = 30) -> Dict[str, Any]:
        """Open SSH, run one safe show command, close SSH, and return structured output."""
        command = normalize_command(command)

        if device not in LAB_DEVICES:
            return {
                "ok": False,
                "error": f"Unknown device '{device}'. Valid devices: {', '.join(LAB_DEVICES)}",
            }

        if not is_safe_show_command(command):
            return {
                "ok": False,
                "device": device,
                "command": command,
                "error": "Blocked by safety policy. Only read-only 'show' commands are allowed, and sensitive/risky commands are blocked.",
            }

        connection = None
        params = self._device_params(device)

        try:
            connection = ConnectHandler(**params)

            if self.secret:
                connection.enable()

            output = connection.send_command(command, read_timeout=read_timeout)

            return {
                "ok": True,
                "device": device,
                "host": LAB_DEVICES[device]["host"],
                "device_type": LAB_DEVICES[device]["device_type"],
                "role": LAB_DEVICES[device]["role"],
                "command": command,
                "output": output,
            }

        except NetMikoAuthenticationException as exc:
            return {
                "ok": False,
                "device": device,
                "host": LAB_DEVICES[device]["host"],
                "error": f"Authentication failed: {exc}",
            }
        except NetMikoTimeoutException as exc:
            return {
                "ok": False,
                "device": device,
                "host": LAB_DEVICES[device]["host"],
                "error": f"SSH timeout or device unreachable: {exc}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "device": device,
                "host": LAB_DEVICES[device]["host"],
                "error": str(exc),
            }
        finally:
            if connection:
                connection.disconnect()

    def get_device_status(self, device: str) -> Dict[str, Any]:
        """Collect basic status from a device."""
        if not VALID_DEVICE_NAME.match(device):
            return {"ok": False, "error": f"Invalid device name: {device}"}

        hostname = self._send_show_command(device, "show hostname")
        version = self._send_show_command(device, "show version")

        return {
            "ok": hostname.get("ok", False) or version.get("ok", False),
            "device": device,
            "role": LAB_DEVICES.get(device, {}).get("role"),
            "management_host": LAB_DEVICES.get(device, {}).get("host"),
            "commands": {
                "show hostname": hostname,
                "show version": version,
            },
        }

    def get_interface_status(self, device: str, interface: Optional[str] = None) -> Dict[str, Any]:
        """Collect interface status from a device."""
        if not VALID_DEVICE_NAME.match(device):
            return {"ok": False, "error": f"Invalid device name: {device}"}

        if interface:
            if not VALID_INTERFACE_NAME.match(interface):
                return {"ok": False, "error": f"Invalid interface name: {interface}"}
            command = f"show interfaces {interface}"
        else:
            command = "show interfaces status"

        return self._send_show_command(device, command)

    def get_bgp_summary(self, device: str) -> Dict[str, Any]:
        """Collect BGP neighbor summary from a device."""
        if not VALID_DEVICE_NAME.match(device):
            return {"ok": False, "error": f"Invalid device name: {device}"}

        # Works on Arista EOS and many Cisco platforms. Adjust for your vendor if needed.
        return self._send_show_command(device, "show ip bgp summary")

    def ping_device(self, target: str, count: int = 4) -> Dict[str, Any]:
        """
        Compatibility helper from the mock lab.

        In this SSH version, this checks SSH reachability if the target is one of the lab devices.
        It does not perform ICMP ping from the network device.
        """
        try:
            resolved_target = resolve_target(target)
        except ValueError as exc:
            return {"ok": False, "target": target, "error": str(exc)}

        # If the target is a known lab device, try to open an SSH session.
        if target in LAB_DEVICES:
            connection = None
            try:
                connection = ConnectHandler(**self._device_params(target))
                prompt = connection.find_prompt()
                return {
                    "ok": True,
                    "target": target,
                    "host": resolved_target,
                    "method": "ssh_connect",
                    "prompt": prompt,
                    "message": "SSH connection successful.",
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "target": target,
                    "host": resolved_target,
                    "method": "ssh_connect",
                    "error": str(exc),
                }
            finally:
                if connection:
                    connection.disconnect()

        return {
            "ok": False,
            "target": target,
            "host": resolved_target,
            "error": "Target is not in LAB_DEVICES. Add it to the inventory or use execute_command from a known device.",
        }

    def execute_command(self, device: str, command: str) -> Dict[str, Any]:
        """Run one safe show command over SSH."""
        if not VALID_DEVICE_NAME.match(device):
            return {"ok": False, "error": f"Invalid device name: {device}"}

        return self._send_show_command(device, command)

    def get_topology_info(self) -> Dict[str, Any]:
        """Return static lab topology information."""
        return {
            "ok": True,
            "devices": LAB_DEVICES,
            "topology": LAB_TOPOLOGY,
        }

    # ------------------------------------------------------------------
    # Core agent loop
    # ------------------------------------------------------------------

    def chat(self, user_message: str, verbose: bool = True, max_iterations: int = 10) -> str:
        """
        Send a message and let the agent autonomously solve the problem.

        Args:
            user_message: User question or instruction.
            verbose: Print tool calls as they happen.
            max_iterations: Safety cap on tool-call rounds.

        Returns:
            Agent's final text response.
        """
        self.conversation_history.append({"role": "user", "content": user_message})

        for _ in range(max_iterations):
            response_msg = self._call_ollama()
            tool_calls = response_msg.get("tool_calls") or []

            if not tool_calls:
                final_text = response_msg.get("content", "").strip()
                self.conversation_history.append({"role": "assistant", "content": final_text})
                return final_text

            # Record the assistant turn with tool calls.
            self.conversation_history.append(response_msg)

            # Execute each tool and feed results back.
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
                    safe_result = self._redact_sensitive(result)
                    print(f"📊 Result: {json.dumps(safe_result, indent=2)}")

                self.conversation_history.append(
                    {
                        "role": "tool",
                        "content": json.dumps(result),
                    }
                )

        return self._call_ollama().get("content", "Max iterations reached.")

    def _call_ollama(self) -> Dict[str, Any]:
        """POST to Ollama /api/chat and return the message dictionary."""
        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation_history

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": self.tools,
            "stream": False,
            "options": {"temperature": 0.2},
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json().get("message", {"role": "assistant", "content": "No response"})
        except requests.exceptions.ConnectionError:
            return {
                "role": "assistant",
                "content": "Error: Cannot connect to Ollama. Is it running? Try: ollama serve",
            }
        except Exception as exc:
            return {"role": "assistant", "content": f"Error: {exc}"}

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Call the matching Python function and return a result dictionary."""
        tool_func = self.tools_map.get(tool_name)

        if not tool_func:
            return {"ok": False, "error": f"Unknown tool: {tool_name}"}

        try:
            result = tool_func(**args)
            return result if isinstance(result, dict) else {"ok": True, "result": str(result)}
        except TypeError as exc:
            return {"ok": False, "error": f"Invalid arguments for {tool_name}: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def _redact_sensitive(data: Any) -> Any:
        """Basic redaction for console logging."""
        if isinstance(data, dict):
            return {k: AgenticNetworkBot._redact_sensitive(v) for k, v in data.items()}
        if isinstance(data, list):
            return [AgenticNetworkBot._redact_sensitive(item) for item in data]
        if isinstance(data, str):
            # This is intentionally conservative. Avoid running show running-config in the first place.
            return data.replace(os.getenv("NETMIKO_PASSWORD", "__NO_PASSWORD_ENV__"), "***")
        return data

    def reset(self):
        """Clear conversation history."""
        self.conversation_history = []


# -----------------------------------------------------------------------------
# Demo and challenge helpers
# -----------------------------------------------------------------------------


def demo_simple_query():
    print("\n" + "=" * 70)
    print("DEMO 1: Real SSH Device Query")
    print("=" * 70)
    bot = AgenticNetworkBot()
    response = bot.chat("SSH to spine1 and tell me its device status.")
    print(f"\n🤖 Agent: {response}")


def demo_multi_device_query():
    print("\n" + "=" * 70)
    print("DEMO 2: Real SSH BGP Check")
    print("=" * 70)
    bot = AgenticNetworkBot()
    response = bot.chat("Check BGP on spine1, spine2, leaf1, and leaf2. Are all sessions healthy?")
    print(f"\n🤖 Agent: {response}")


def demo_troubleshooting():
    print("\n" + "=" * 70)
    print("DEMO 3: Real SSH Troubleshooting")
    print("=" * 70)
    bot = AgenticNetworkBot()
    response = bot.chat(
        "Investigate leaf2. Check interface status and BGP, then tell me if you see a problem."
    )
    print(f"\n🤖 Agent: {response}")


def demo_topology_analysis():
    print("\n" + "=" * 70)
    print("DEMO 4: Topology-Aware SSH Analysis")
    print("=" * 70)
    bot = AgenticNetworkBot()
    response = bot.chat("Which device appears to have the most BGP peers and why?")
    print(f"\n🤖 Agent: {response}")


def interactive_mode():
    print("\n" + "=" * 70)
    print("🤖 Interactive Agentic Network Bot with Netmiko SSH")
    print("=" * 70)
    print("Available devices: spine1, spine2, leaf1, leaf2")
    print("Type 'quit' to exit, 'reset' to clear history")
    print("Only read-only show commands are allowed through execute_command.")
    print("=" * 70)

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

            response = bot.chat(user_input, verbose=True)
            print(f"\n🤖 Agent: {response}")

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n🎯 Lab 4B: Agentic Network Bot with Real SSH  (Netmiko + Ollama)")
    print("=" * 70)
    print("This version connects to real devices over SSH.")
    print("Make sure Ollama is running:      ollama serve")
    print("Make sure model is pulled:        ollama pull deepseek-r1:8b")
    print("Install dependencies:             pip install -r requirements.txt")
    print("Set credentials with env vars or enter them when prompted.")
    print("=" * 70)

    # Start here for real labs:
    interactive_mode()

    # Or comment interactive_mode() above and uncomment a demo:
    # demo_simple_query()
    # demo_multi_device_query()
    # demo_troubleshooting()
    # demo_topology_analysis()
