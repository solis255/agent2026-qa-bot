# Quick Start Guide
## Get Running in 5 Minutes

**100% Free using Ollama - No API keys required!**

This guide gets you from zero to running your first lab in 5 minutes.

## Prerequisites

- macOS, Linux, or Windows
- 5-10 minutes of time
- Internet connection (for initial setup only)

## Installation

### 1. Install Ollama (2 min)

**macOS:**
```bash
brew install ollama
```

**Linux:**
```bash
curl https://ollama.ai/install.sh | sh
```

**Windows:**
Download from https://ollama.com/download

### 2. Pull Model (2 min)

```bash
ollama pull llama3.2:3b
ollama pull deepseek-r1:8b
```

This downloads ~2GB. Only needed once!

### 3. Clone Repository (1 min)

```bash
git clone https://github.com/PacktPublishing/Building-AI-Agents-for-Network-Operations
cd Building-AI-Agents-for-Network-Operations

# Install Python dependencies (just requests!)
pip3 install -r requirements.txt
```

## Run Your First Lab

```bash
# Test Ollama connection
python3 labs/lab1-ollama/simple_ollama_test.py
```

**Expected output:**
```
🤖 Ollama API Test - AI Networking Workshop
==================================================

📝 Test 1: Simple Chat
Response: OSPF (Open Shortest Path First) is a link-state routing protocol...
Tokens: 156
```

**✅ Success!** You're now running AI agents locally!

## What's Next?

### All Labs Work with Ollama (Free!)

```bash
# Lab 1: Ollama basics
python3 labs/lab1-ollama/simple_ollama_test.py

# Lab 2: Prompt engineering
python3 labs/lab2-prompts/prompt_engineering_race.py

# Lab 3: Network chatbot
python3 labs/lab3-chatbot/chatbot_v2_with_memory.py

# Lab 4: Autonomous agent ⭐
python3 labs/lab4-agentic/agentic_network_bot_ollama.py
```

**All 4 labs - $0 cost!**

## Troubleshooting

**Ollama not connecting?**
```bash
# Start Ollama service
ollama serve
```

**Model not found?**
```bash
# Check installed models
ollama list

# Pull if missing
ollama pull llama3.2:3b
```

**Import errors?**
```bash
pip3 install -r requirements.txt --upgrade
```

**Need help?**
- Run: `python3 examples/test_setup.py`
- Check: `docs/SETUP_GUIDE.md`
- Open: GitHub Issue

## Skip to the Good Stuff

Want to see the autonomous agent in action?

```bash
# Jump to Lab 4 (star lab)
cd labs/lab4-agentic
python3 agentic_network_bot_ollama.py
```

This runs an autonomous AI agent that troubleshoots a mock network!

**Sample interaction:**
```
👤 User: Check if leaf2 has any issues
🔧 Agent is calling: get_device_status({"device": "leaf2"})
🔧 Agent is calling: get_bgp_summary({"device": "leaf2"})
🔧 Agent is calling: get_interface_status({"device": "leaf2", "interface": "Ethernet3"})
🤖 Agent: leaf2 has two issues:
  leaf2 has 1/2 BGP peers established
neighbor 10.1.2.2 is Idle
  Recommend checking physical connectivity and BGP configuration.
```

---

**Full setup guide:** `docs/SETUP_GUIDE.md`  
**Workshop outline:** `docs/COMPLETE_WORKSHOP_OUTLINE.md`

**Cost:** $0 Forever  
**API Keys:** None Required  
**Privacy:** 100% Local Processing
