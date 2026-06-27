# Lab 4 README: Agentic Network Bot

This lab shows students how to build an **AI network agent** that can answer questions by calling network tools on its own. Instead of only responding from memory, the bot can decide when to check device status, BGP neighbors, interfaces, topology, or run read-only show commands. 

---

## What This Script Does

This script creates an **Agentic Network Bot** using:

* **Ollama** running locally
* **deepseek-r1:8b**
* Python tool calling
* Mock network devices
* A spine-leaf network topology

The agent can answer questions like:

```text
What's the status of spine1?
```

Or more advanced questions like:

```text
Are all BGP sessions up in the network?
```

The important part is this:

> The AI decides which tool to call, runs the tool, reads the result, and then gives the student a final answer.

---

## Available Lab Devices

The bot knows about four mock devices:

```text
spine1 - Core spine switch
spine2 - Core spine switch
leaf1  - Leaf/access switch
leaf2  - Leaf/access switch
```

The lab topology is a basic spine-leaf design:

```text
spine1        spine2
  | \          / |
  |  \        /  |
leaf1       leaf2
```

---

## Requirements

Before running the script, students need:

* Python 3 installed
* Ollama installed
* The `deepseek-r1:8b` model downloaded
* The mock device file available in the expected `examples` folder
* The Python `requests` package installed

---

## Step 1: Start Ollama

Open a terminal and run:

```bash
ollama serve
```

Leave this terminal running.

---

## Step 2: Pull the Model

In a second terminal, run:

```bash
ollama pull deepseek-r1:8b
```

This downloads the local model used by the lab.

---

## Step 3: Create a Python Virtual Environment

From your project folder, run:

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## Step 4: Install Dependencies

```bash
pip install requests
```

---

## Step 5: Run the Lab

Run the Python file:

```bash
python lab4_agentic_network_bot.py
```

Depending on your filename, you may need to replace `lab4_agentic_network_bot.py` with the actual name of your script.

By default, the script runs this demo:

```python
demo_simple_query()
```

That asks:

```text
What's the status of spine1?
```

---

# How the Script Works

## 1. The Bot Has a System Prompt

The system prompt tells the AI:

* You are a network engineer assistant
* These are the available devices
* This is the network design
* Troubleshoot systematically
* Use facts from tool output

This helps the AI behave like a network engineer instead of a generic chatbot.

---

## 2. The Bot Has Tools

The bot can call these tools:

```python
get_device_status
get_interface_status
get_bgp_summary
ping_device
execute_command
get_topology_info
```

Each tool represents something a network engineer might do.

For example:

```python
get_bgp_summary("leaf1")
```

Would return BGP neighbor information for `leaf1`.

---

## 3. The Bot Sends Tools to Ollama

Inside `_call_ollama()`, the script sends:

```python
"messages": messages,
"tools": self.tools,
```

That tells the model:

> Here is the conversation.
> Here are the tools you are allowed to use.

The model can then respond with either:

1. A normal answer
2. A tool call request

---

## 4. The Bot Executes Tool Calls

When the model chooses a tool, this part runs:

```python
result = self._execute_tool(tool_name, tool_args)
```

The result is then added back into the conversation as a tool response.

That lets the AI read real tool output before giving a final answer.

---

## 5. The Bot Keeps Looping

The bot keeps going until the AI no longer asks for another tool.

That is what makes it **agentic**.

It can do multi-step work like:

1. Check the topology
2. Check leaf interfaces
3. Find the down interface
4. Determine what it connects to
5. Explain the issue

---

# How to Run Different Demos

At the bottom of the script, you will see this section:

```python
demo_simple_query()
# demo_multi_device_query()
# demo_troubleshooting()
# demo_topology_analysis()
```

Only `demo_simple_query()` runs by default.

To run another demo, remove the `#`.

For example, to run the BGP demo:

```python
# demo_simple_query()
demo_multi_device_query()
# demo_troubleshooting()
# demo_topology_analysis()
```

Then run:

```bash
python lab4_agentic_network_bot.py
```

---

# Demo Options

## Demo 1: Simple Device Query

```python
demo_simple_query()
```

Question asked:

```text
What's the status of spine1?
```

Good for showing students a basic one-tool interaction.

---

## Demo 2: Multi-Device Query

```python
demo_multi_device_query()
```

Question asked:

```text
Are all BGP sessions up in the network?
```

Good for showing the agent checking multiple devices.

---

## Demo 3: Troubleshooting

```python
demo_troubleshooting()
```

Question asked:

```text
I notice leaf2 has an interface down. Can you investigate and tell me which interface and what it connects to?
```

Good for teaching multi-step reasoning.

---

## Demo 4: Topology Analysis

```python
demo_topology_analysis()
```

Question asked:

```text
Which device has the most BGP peers and why?
```

Good for showing topology-aware analysis.

---

# How to Use Interactive Mode

To chat with the bot directly, uncomment this line:

```python
# interactive_mode()
```

Change it to:

```python
interactive_mode()
```

You may also want to comment out the default demo:

```python
# demo_simple_query()
interactive_mode()
```

Then run the script.

You can now ask your own questions:

```text
What interfaces are down?
```

```text
Check BGP on all devices.
```

```text
What does the topology look like?
```

```text
Run show version on spine1.
```

To exit:

```text
quit
```

To clear memory:

```text
reset
```

---

# How Students Can Modify the Script

## 1. Change the Model

At the top of the file, change:

```python
MODEL = "deepseek-r1:8b"
```

Example:

```python
MODEL = "llama3.1:8b"
```

Then pull the model first:

```bash
ollama pull llama3.1:8b
```

Larger models may give better reasoning, but they may run slower.

---

## 2. Change the Temperature

Inside `_call_ollama()`, find:

```python
"options": {"temperature": 0.3},
```

Lower temperature gives more consistent answers:

```python
"options": {"temperature": 0.1},
```

Higher temperature gives more creative answers:

```python
"options": {"temperature": 0.7},
```

For network troubleshooting, I recommend keeping it low:

```python
temperature = 0.1 to 0.3
```

---

## 3. Change the User Question

Inside any demo function, change the prompt.

Example:

```python
response = bot.chat("What's the status of spine1?")
```

Change it to:

```python
response = bot.chat("Check all interfaces on leaf2 and tell me if anything is down.")
```

Or:

```python
response = bot.chat("Create a short network health report for all devices.")
```

---

## 4. Turn Verbose Mode On or Off

Verbose mode shows the tools being called.

Example:

```python
response = bot.chat(user_input, verbose=True)
```

This prints output like:

```text
🔧 Agent calling: get_device_status({"device": "spine1"})
📊 Result: ...
```

For teaching, keep this on.

For cleaner output, change it to:

```python
response = bot.chat(user_input, verbose=False)
```

---

## 5. Change the Maximum Number of Tool Rounds

The chat function includes:

```python
max_iterations: int = 10
```

This prevents the agent from calling tools forever.

You can increase it:

```python
response = bot.chat("Troubleshoot the whole network", max_iterations=15)
```

Or reduce it:

```python
response = bot.chat("Check spine1", max_iterations=3)
```

For students, `10` is a safe default.

---

## 6. Add a New Tool

To add a new tool, students need to update two places.

### Step 1: Add it to `tools_map`

Example:

```python
self.tools_map = {
    "get_device_status": get_device_status,
    "get_interface_status": get_interface_status,
    "get_bgp_summary": get_bgp_summary,
    "ping_device": ping_device,
    "execute_command": execute_command,
    "get_topology_info": get_topology_info,
    "get_vlan_info": get_vlan_info,
}
```

### Step 2: Add a Tool Schema

Example:

```python
{
    "type": "function",
    "function": {
        "name": "get_vlan_info",
        "description": "Get VLAN information from a network device",
        "parameters": {
            "type": "object",
            "properties": {
                "device": {
                    "type": "string",
                    "description": "Device hostname"
                }
            },
            "required": ["device"]
        }
    }
}
```

Now the model knows the tool exists and how to call it.

---

# Example Student Modifications

## Result 1: Create a Full Network Health Check

Change the default demo prompt to:

```python
response = bot.chat(
    "Create a full network health report. Check device status, interfaces, and BGP for all devices."
)
```

Expected behavior:

* Agent checks multiple devices
* Agent calls several tools
* Agent summarizes health of the network

---

## Result 2: Focus Only on BGP

Use:

```python
response = bot.chat(
    "Check BGP on spine1, spine2, leaf1, and leaf2. Tell me if any peers are down."
)
```

Expected behavior:

* Agent calls `get_bgp_summary`
* Agent compares results
* Agent reports BGP health

---

## Result 3: Investigate a Device Problem

Use:

```python
response = bot.chat(
    "Something seems wrong with leaf2. Investigate interfaces and BGP, then explain the most likely issue."
)
```

Expected behavior:

* Agent checks leaf2 interfaces
* Agent checks BGP
* Agent correlates the issue

---

## Result 4: Run a Show Command

Use:

```python
response = bot.chat(
    "Run show version on spine1 and summarize the result."
)
```

Expected behavior:

* Agent calls `execute_command`
* Agent runs a read-only show command
* Agent summarizes the output

---

# Troubleshooting Common Issues

## Error: Cannot connect to Ollama

You may see:

```text
Error: Cannot connect to Ollama. Is it running? Try: ollama serve
```

Fix:

```bash
ollama serve
```

Then rerun the script.

---

## Error: Model Not Found

If Ollama says the model is missing, run:

```bash
ollama pull deepseek-r1:8b
```

---

## Error: No module named requests

Install the dependency:

```bash
pip install requests
```

---

## Error: No module named mock_network_devices

The script expects the mock device file to be in an `examples` folder two levels above the script.

This line controls that path:

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'examples'))
```

If your folder structure is different, either:

1. Move `mock_network_devices.py` into the expected `examples` folder
2. Update the path in the script
3. Place `mock_network_devices.py` in the same folder and simplify the import

Example simple version:

```python
from mock_network_devices import (
    get_device_status,
    get_interface_status,
    get_bgp_summary,
    ping_device,
    execute_command,
    get_topology_info,
    MockNetworkDevice
)
```

---

# Teaching Notes

This lab is important because it shows the difference between a chatbot and an agent.

A normal chatbot answers from the prompt.

An agent can:

1. Read the user’s request
2. Decide what information it needs
3. Call tools
4. Read the tool results
5. Make another decision
6. Give a final answer

That is the big idea.

For network operations, this means the AI is not just writing configs or explaining BGP.

It is starting to behave like an assistant that can interact with network systems.

---

# Key Takeaways

By the end of this lab, students should understand:

* How Ollama can run a local LLM with no API keys
* How tool calling works
* How an AI agent decides which function to call
* How mock network devices can simulate real infrastructure
* How multi-step troubleshooting works
* How the same pattern could later be connected to real devices, APIs, or automation platforms

The big lesson:

> Tool calling turns an LLM from a text generator into an operator that can take action against systems.
