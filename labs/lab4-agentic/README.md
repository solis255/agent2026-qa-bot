# Lab 4: Agentic Network Bot

Build an autonomous AI agent that operates network devices using **100% free Ollama**.

This lab uses `deepseek-r1:8b` for the agentic workflow. The earlier prompt, parsing, and chatbot labs use `llama3.2:3b` as their baseline model.

## Overview

This lab combines everything you've learned:
- LLM fundamentals
- Prompt engineering  
- Tool calling (with structured prompts)
- Conversation memory
- Agentic reasoning

## What You'll Build

A complete AI agent that can:
- Autonomously investigate network issues
- Query multiple devices
- Make multi-step decisions
- Troubleshoot intelligently

**All running locally with Ollama - no API keys required!**

## Mock Network Topology

```
spine1 (192.168.0.11) ─┬─ leaf1 (192.168.0.21)
                       └─ leaf2 (192.168.0.22)
spine2 (192.168.0.12) ─┘
```

## Available Tools

1. `get_device_status()` - Device info
2. `get_bgp_summary()` - BGP neighbors
3. `get_interface_status()` - Interface state
4. `ping_device()` - Reachability
5. `execute_command()` - Show commands
6. `get_topology_info()` - Network structure

## Running the Lab

```bash
# Pull the Lab 4 model if needed
ollama pull deepseek-r1:8b

# Ollama version (recommended - 100% free!)
python3 agentic_network_bot_ollama.py
```

## How It Works

### Tool Calling with Ollama

Since Ollama doesn't have native function calling, we use structured prompts:

```
User: "Check if leaf2 has any issues"

↓

LLM outputs:
TOOL: get_device_status
ARGS: {"device": "leaf2"}

↓

We parse and execute the tool

↓

Feed results back to LLM

↓

LLM decides: call another tool or answer
```

This achieves autonomous behavior without paid APIs!

## Example Queries

```python
bot = AgenticNetworkBot()

# Simple
bot.chat("What's the status of spine1?")

# Complex (multi-step)
bot.chat("Are all BGP sessions up?")

# Troubleshooting
bot.chat("Something is wrong - investigate")
```

## Key Concepts

- **Autonomous**: Agent decides which tools to call
- **Multi-step**: Can call multiple tools to solve problems
- **Local**: Everything runs on your laptop
- **Free**: Zero cost forever
- **Production pattern**: The same pattern can later be adapted for real devices with proper safety controls, credential handling, logging, and approval gates

## Future Real-Device Adaptation

Live network access is optional and advanced. In a controlled lab, you can adapt the mock tool layer to call real SSH or API backends while keeping safety controls outside the agent:

```python
# Mock (workshop)
def get_device_status(device):
    return MOCK_DEVICES.get(device)

# Real-device adapter sketch
import paramiko
def get_device_status(device):
    ssh = paramiko.SSHClient()
    ssh.connect(device, ...)
    # Execute commands, parse output
    return parsed_data
```

The agent-facing pattern can stay similar, but real-device use needs validation, credential handling, logging, and approval gates before it is suitable for operational environments.
