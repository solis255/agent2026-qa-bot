# Lab 4: Agentic Network Bot

This lab uses the TJU competition API's OpenAI-compatible native Function Calling. The model selects a tool, Python executes the controlled function, and the result is returned with the matching `tool_call_id` until the model produces a final answer.

## Run the mock-device version

Configure the project-root `.env`, activate `.venv`, and run:

```powershell
python labs\lab4-agentic\agentic_network_bot.py
```

`agentic_network_bot_ollama.py` is now only a compatibility launcher for older course commands; it imports the same TJU API implementation.

## Agent flow

1. Send the system prompt, conversation, and `tools` schemas.
2. Read the assistant's native `tool_calls`.
3. Validate and execute functions from `tools_map`.
4. Append each result as a `tool` message with its `tool_call_id`.
5. Repeat until a final response or the six-round safety cap.

Available mock tools include device status, interface status, BGP summary, reachability, topology information, and safe show commands.

## Real SSH version

```powershell
python labs\lab4-agentic\lab4b_agentic_network_bot_netmiko.py
```

Set `NETMIKO_USERNAME`, `NETMIKO_PASSWORD`, optional `NETMIKO_SECRET`, and per-device host overrides in the process environment. The generic command tool permits only read-only `show` commands and blocks risky or secret-bearing variants.

The model API Key must remain only in the root `.env`. Never place it in source code or console output.
