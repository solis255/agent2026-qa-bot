Here’s a `README.md` you can use for the uploaded script. It explains **Lab 3 Part C: Stateful Chatbot with Live SSH Context**, including what the script does, how it works, and comments for the important sections. 

````markdown
# Lab 3 Part C: Stateful Chatbot with Live SSH Context

## Overview

This lab builds on the previous chatbot examples by adding **live network device context**.

Instead of only remembering the conversation, this chatbot can also answer questions based on current network device state.

The script supports two modes:

1. **Mock Mode**
   - Uses fake/sample network data.
   - Great for workshops, demos, and testing without real devices.

2. **Live SSH Mode**
   - Connects to real network devices using Netmiko.
   - Pulls live command output from switches.
   - Injects that live data into the chatbot prompt.

By default, the script runs in **mock mode** so it works without needing real lab equipment.

---

## What This Script Demonstrates

This script demonstrates three important AI automation concepts:

### 1. Stateful Chatbot Memory

The chatbot remembers previous user and assistant messages during the session.

That means you can ask follow-up questions like:

```text
What did I just ask you about?
````

And the chatbot can answer because it has conversation history.

---

### 2. Live Network Context

The chatbot is given network device state at startup.

That device state includes:

* Interface status
* Loopback IPs
* Management IPs
* BGP neighbor status

This allows the chatbot to answer questions like:

```text
Which interfaces are currently down?
```

Or:

```text
Are all BGP sessions healthy?
```

---

### 3. Refreshable Context

The script supports a `refresh` command.

This re-fetches the current device state and rebuilds the chatbot system prompt.

That means the chatbot can update what it knows during the conversation.

---

## Requirements

### Required

* Python 3
* Ollama running locally
* A local model such as `llama3.2:3b`

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Start Ollama:

```bash
ollama serve
```

Pull the model:

```bash
ollama pull llama3.2:3b
```

---

## How to Run

Run the script:

```bash
python chatbot_v3_live_ssh_context.py
```

By default, it runs in mock mode:

```python
USE_MOCK = True
```

This means no real devices are needed.

---

## Switching to Real Devices

To use real SSH devices, change this:

```python
USE_MOCK = True
```

To this:

```python
USE_MOCK = False
```

Then update the device configuration:

```python
DEVICE_CONFIG = {
    "spine1": {
        "device_type": "arista_eos",
        "host": "192.168.0.11",
        "username": "admin",
        "password": "admin",
        "port": 22
    }
}
```

Each device entry tells Netmiko how to SSH into that device.

---

## High-Level Flow

The script works like this:

```text
Start script
   |
   v
Load device config
   |
   v
Collect mock or live SSH device state
   |
   v
Build system prompt with network state
   |
   v
Send user question + history + device context to Ollama
   |
   v
Return chatbot answer
```

---

## Important Sections Explained

---

## 1. Mock vs Live SSH Toggle

```python
USE_MOCK = True
```

This controls whether the script uses mock data or connects to real devices.

When `USE_MOCK` is `True`, the chatbot uses the sample interface and BGP data already inside the script.

When `USE_MOCK` is `False`, the chatbot tries to connect to real devices using SSH and Netmiko.

This makes the script workshop-friendly because everyone can run it even without network gear.

---

## 2. Device Configuration

```python
DEVICE_CONFIG = {
    "spine1": {
        "device_type": "arista_eos",
        "host": "192.168.0.11",
        "username": "admin",
        "password": "admin",
        "port": 22
    }
}
```

This dictionary defines the devices the script can connect to.

Each device has:

* `device_type`: The Netmiko platform type
* `host`: The management IP address
* `username`: SSH username
* `password`: SSH password
* `port`: SSH port, usually `22`

The example topology includes:

* `spine1`
* `spine2`
* `leaf1`
* `leaf2`

---

## 3. Mock Interface Data

```python
_MOCK_INT_BRIEF = {
    "leaf1": (
        "Ethernet1  unassigned  up    up\n"
        "Ethernet2  unassigned  up    up\n"
        "Ethernet3  unassigned  down  down\n"
        "Loopback0  10.0.1.21   up    up\n"
        "Mgmt1      192.168.0.21 up   up"
    )
}
```

This is fake interface output that looks like something you might get from a real switch.

For example, `leaf1` has:

```text
Ethernet3 down/down
```

That gives the chatbot enough context to answer:

```text
Which interfaces are down?
```

---

## 4. Mock BGP Data

```python
_MOCK_BGP = {
    "leaf2": "10.1.1.2 65001 Estab 2d03h  50\n10.1.2.2 65001 Idle  0:00   0",
}
```

This is fake BGP neighbor output.

In this example, `leaf2` has one BGP neighbor in an `Idle` state.

That gives the chatbot enough context to identify a BGP problem.

---

# LiveDeviceContext Class

The `LiveDeviceContext` class is responsible for collecting network state.

Think of this class as the data collector.

It either:

* Pulls data from mock dictionaries
* Or connects to real devices with SSH

Then it builds one large text snapshot that gets inserted into the chatbot prompt.

---

## Class Initialization

```python
def __init__(self, devices: List[str] = None):
    self.devices = devices or list(DEVICE_CONFIG.keys())
    self.snapshot: str = ""
    self.refresh()
```

When the class starts, it:

1. Loads the list of devices.
2. Creates an empty snapshot.
3. Immediately calls `refresh()`.

That means the chatbot collects device state as soon as it starts.

---

## Refreshing Device State

```python
def refresh(self):
    """(Re-)fetch device state and rebuild the snapshot."""
```

The `refresh()` method collects current state from each device.

For every device, it runs two commands:

```python
show ip interface brief
show bgp summary
```

Then it builds a snapshot like this:

```text
--- spine1 ---
Interfaces:
...

BGP neighbors:
...
```

That full snapshot becomes part of the chatbot’s system prompt.

---

## Fetching Data

```python
def _fetch(self, device: str, command: str) -> str:
```

This method decides where the command output comes from.

If mock mode is enabled:

```python
if USE_MOCK:
    return self._mock(device, command)
```

It returns fake sample data.

If live mode is enabled, it tries to import Netmiko:

```python
from netmiko import ConnectHandler
```

Then it connects to the device and runs the command:

```python
with ConnectHandler(**cfg) as conn:
    return conn.send_command(command)
```

If SSH fails, it falls back to mock data.

That is useful for workshops because one bad device connection does not break the entire demo.

---

## Mock Data Lookup

```python
def _mock(self, device: str, command: str) -> str:
```

This method returns fake output based on the command.

If the command contains `interface`, it returns interface data.

If the command contains `bgp`, it returns BGP data.

Example:

```python
if "interface" in command.lower():
    return _MOCK_INT_BRIEF.get(dev, f"[mock] no data for {dev}")
```

This keeps the rest of the script simple because the chatbot does not care whether the data came from mock data or SSH.

---

# LiveNetworkChatbot Class

The `LiveNetworkChatbot` class is the actual chatbot.

It combines:

* The LLM model
* Conversation history
* Network device context
* Prompt building
* Ollama API calls

---

## Chatbot Initialization

```python
def __init__(self, model: str = "llama3.2:3b"):
    self.model = model
    self.conversation_history: List[Dict[str, str]] = []
    self.context = LiveDeviceContext()
    self._build_system_prompt()
```

When the chatbot starts, it:

1. Sets the model name.
2. Creates empty conversation history.
3. Collects device context.
4. Builds the system prompt.

The important part is this:

```python
self.context = LiveDeviceContext()
```

That is where the device data is collected before the chatbot answers any questions.

---

## Building the System Prompt

```python
def _build_system_prompt(self):
```

The system prompt tells the model who it is and what network state it has access to.

The prompt includes:

```python
CURRENT NETWORK STATE:
{self.context.snapshot}
```

That means the LLM sees the latest network snapshot before answering.

This is the key idea in the lab.

The chatbot is not magically connected to the network.

Instead, the script collects network data first, then places that data into the prompt.

---

## Refreshing Chatbot Context

```python
def refresh_context(self):
    """Re-fetch device state and rebuild system prompt."""
```

This method allows the chatbot to update its network knowledge during the conversation.

It does two things:

```python
self.context.refresh()
self._build_system_prompt()
```

So when the user types:

```text
refresh
```

The chatbot re-collects the network state and rebuilds the prompt.

---

## Sending a Chat Message

```python
def chat(self, user_message: str) -> str:
```

This is the main chat function.

It does four things:

### Step 1: Save the user message

```python
self.conversation_history.append({
    "role": "user",
    "content": user_message
})
```

This gives the chatbot memory.

---

### Step 2: Build the full prompt

```python
prompt = self._build_prompt()
```

The prompt includes:

* System prompt
* Current network state
* Previous user messages
* Previous assistant responses
* The latest user question

---

### Step 3: Send the prompt to Ollama

```python
resp = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": self.model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "num_predict": 1024
        },
    },
    timeout=60,
)
```

This sends the prompt to the local Ollama API.

The options mean:

* `temperature: 0.5`: Balanced creativity and accuracy
* `num_predict: 1024`: Allows longer responses
* `stream: False`: Waits for the full answer before returning

---

### Step 4: Save and return the assistant response

```python
assistant_msg = resp.json().get("response", "").strip()
self.conversation_history.append({
    "role": "assistant",
    "content": assistant_msg
})
return assistant_msg
```

The assistant response is saved into history so future questions can reference it.

---

## Prompt Building

```python
def _build_prompt(self) -> str:
```

This method builds the full prompt that gets sent to Ollama.

It starts with the system prompt:

```python
parts = [self.system_prompt, "\n\n"]
```

Then it adds each message in the conversation history:

```python
for msg in self.conversation_history:
    prefix = "User" if msg["role"] == "user" else "Assistant"
    parts.append(f"{prefix}: {msg['content']}\n")
```

Finally, it adds:

```python
Assistant:
```

That tells the model it is the assistant’s turn to respond.

---

## Resetting Memory

```python
def reset(self):
    self.conversation_history = []
```

This clears the conversation history.

It does not refresh the device data.

It only clears the chat memory.

---

## Getting History Length

```python
def get_history_length(self) -> int:
    return len(self.conversation_history)
```

This returns how many messages are currently stored in memory.

The script prints this after every interactive response.

---

# Demo Mode

When the script runs, it starts with a scripted demo.

```python
demo_questions = [
    "Which interfaces are currently down?",
    "Are all BGP sessions healthy? Any sessions that are Idle?",
    "What did I just ask you about?",
]
```

These questions test three capabilities:

| Question                             | What It Tests       |
| ------------------------------------ | ------------------- |
| Which interfaces are currently down? | Device context      |
| Are all BGP sessions healthy?        | BGP context         |
| What did I just ask you about?       | Conversation memory |

---

# Interactive Mode

After the demo, the script starts an interactive chat loop.

```text
Commands: 'quit' to exit | 'reset' to clear history | 'refresh' to re-fetch device state
```

You can type normal questions like:

```text
Which leaf switch has a BGP issue?
```

Or:

```text
What interface is down on leaf1?
```

You can also use special commands.

---

## Interactive Commands

### quit

Exits the chatbot.

```text
quit
```

You can also use:

```text
exit
q
```

---

### reset

Clears conversation history.

```text
reset
```

Use this when you want to start a clean conversation.

---

### refresh

Re-fetches device state.

```text
refresh
```

In mock mode, it reloads the mock data.

In live SSH mode, it reconnects to devices and runs the commands again.

---

# Why This Matters

This lab shows an important pattern for AI in network operations.

The LLM itself does not know your live network.

It only knows what you give it.

So the workflow is:

```text
Collect network state
Inject it into the prompt
Ask the model to reason over that data
Return an answer
```

That pattern is the foundation for more advanced network AI agents.

This is how you move from:

```text
AI that writes configs
```

To:

```text
AI that understands current network state and helps troubleshoot
```

---

# Example Questions to Try

Once the chatbot is running, try asking:

```text
Which interfaces are down?
```

```text
Is there a BGP neighbor in Idle?
```

```text
Which device has the unhealthy BGP session?
```

```text
What is the management IP of leaf2?
```

```text
What did I ask you first?
```

```text
Based on the current state, what should I investigate?
```

---

# Example Expected Behavior

Because the mock data includes down interfaces on `leaf1` and `leaf2`, the chatbot should be able to identify:

```text
leaf1 Ethernet3 is down/down
leaf2 Ethernet3 is down/down
```

Because the mock BGP data includes an Idle neighbor on `leaf2`, the chatbot should also be able to identify:

```text
leaf2 has a BGP neighbor in Idle state: 10.1.2.2
```

---

# Key Takeaways

By the end of this lab, you should understand:

* How to give a chatbot memory
* How to inject live or mock network state into a prompt
* How to use Netmiko to collect device data
* How to refresh chatbot context during a session
* Why context matters when building AI tools for network operations

---

# Workshop Notes

For workshop delivery, keep:

```python
USE_MOCK = True
```

This makes the lab easy for everyone to run.

After the workshop, students can set:

```python
USE_MOCK = False
```

Then update `DEVICE_CONFIG` with their own devices.

---

# Suggested Improvements

Here are a few ways to improve the script later:

1. Add more commands, such as:

```text
show interfaces status
show ip route
show lldp neighbors
show running-config
```

2. Store device snapshots in a file.

3. Add structured JSON parsing for command output.

4. Add support for multiple vendors.

5. Add safer prompting to prevent the chatbot from guessing.

6. Add tool-calling so the chatbot can request fresh command output dynamically.

---

# Final Thought

This script is a great bridge between a simple chatbot and a real network operations assistant.

The big lesson is this:

> The value is not just in the model.
> The value is in the context you give the model.

In this lab, that context is live or mock device state.

That is what allows the chatbot to move from generic answers to useful network troubleshooting assistance.

```
```
