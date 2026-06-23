# AI Networking Workshop: From LLMs to Production Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![macOS Compatible](https://img.shields.io/badge/macOS-compatible-green.svg)]()
[![100% Free](https://img.shields.io/badge/cost-$0-brightgreen.svg)]()

> **Build autonomous AI agents for network operations** - A hands-on workshop teaching network engineers to create production-ready AI systems from scratch. **100% free using Ollama - no API keys required!**

## 🎯 Workshop Overview

**Duration:** 3.25 hours  
**Format:** Hands-on labs with live instruction  
**Level:** Intermediate network engineers  
**Platform:** 100% macOS compatible (no VM needed!)  
**Cost:** $0 - Completely free using local Ollama

### What Makes This Workshop Unique

While most AI workshops teach you to *use* AI tools like ChatGPT and GitHub Copilot, this workshop teaches you to **build AI agents from scratch**.

**You'll learn to:**
- ✅ Understand how LLMs actually work (tokens, context windows, temperature)
- ✅ Write production-quality prompts using systematic frameworks
- ✅ Build stateful chatbots with conversation memory
- ✅ Create autonomous agents with tool calling
- ✅ Deploy agents to network infrastructure

**Key Differentiator:** Focus on building, not just using. You'll create a complete autonomous network agent that can troubleshoot, investigate, and operate your network devices - **all running locally on your laptop for free!**

## 🚀 Quick Start

### Prerequisites

```bash
# Check your versions
python3 --version  # Need 3.10+
git --version

# Install Ollama (macOS)
brew install ollama

# Or download from: https://ollama.com/download
```

### Installation

```bash
# Clone the repository
git clone https://github.com/sifbaksh/ai-networking-workshop.git
cd ai-networking-workshop

# Install Python dependencies (just requests!)
pip3 install -r requirements.txt

# Pull LLM model (one-time, ~2GB download)
ollama pull llama3.2:3b

# Test the environment
python3 examples/test_setup.py
```

### Run Your First Lab

```bash
# Lab 1: Local LLM interaction
python3 labs/lab1-ollama/simple_ollama_test.py

# Lab 2: Prompt engineering
python3 labs/lab2-prompts/prompt_engineering_race.py

# Lab 3: Network chatbot with memory
python3 labs/lab3-chatbot/chatbot_v2_with_memory.py

# Lab 4: Autonomous agentic network bot ⭐
python3 labs/lab4-agentic/agentic_network_bot_ollama.py
```

**That's it!** All labs work with Ollama - no API keys, no cloud services, no cost.

## 📚 Workshop Structure

### Theory Modules (85 minutes)

**Module 1: How LLMs Work** (20 min)
- Tokenization and embeddings
- Context windows and attention
- Temperature and sampling
- Why local models (Ollama) work great

**Module 2: Prompt Engineering** (15 min)
- The RACE framework
- Persona, Examples, kNowledge, Evaluation
- Production prompt templates

**Module 3: LLM APIs** (15 min)
- Ollama API basics
- Building conversation history
- Managing context windows

**Module 4: Agentic Patterns** (20 min)
- What makes an agent autonomous
- Tool calling with structured prompts
- Multi-step reasoning loops

**Module 5: Production Path** (10 min)
- Mock devices → Real SSH
- Error handling and retries
- Deployment strategies

### Hands-On Labs (110 minutes)

**Lab 1: Ollama + Network Prompts** (15 min)
- Call Ollama API from Python
- Control generation parameters
- Parse structured JSON output
- Compare models (llama3.2 vs llama3.1)

**Lab 2: Prompt Engineering** (25 min)
- Apply RACE framework
- Build config parser prompts
- Create alert triage prompts
- Test and iterate

**Lab 3: Network Chatbot** (25 min)
- Build stateless chatbot (see the problem)
- Add conversation memory (fix it)
- Manage context windows
- Interactive CLI

**Lab 4: Agentic Network Bot** ⭐ (35 min)
- Define network tools (device status, BGP, interfaces)
- Implement autonomous tool calling
- Multi-step troubleshooting
- Test on mock network

**Break:** 10 minutes

## 🎁 What's Included

### Complete Lab Code
- ✅ Lab 1: Ollama basics (2 Python files)
- ✅ Lab 2: Prompt engineering (2 files)
- ✅ Lab 3: Chatbot (2 files)
- ✅ Lab 4: Agentic bot (1 file) ⭐

### Mock Network Infrastructure
- ✅ 4-device spine-leaf topology
- ✅ Realistic Arista cEOS behavior
- ✅ Built-in troubleshooting scenarios
- ✅ BGP, interfaces, reachability

### Documentation
- ✅ Complete workshop outline (23 pages)
- ✅ Setup guides (macOS, Linux, Windows)
- ✅ Prompt template library
- ✅ Production migration examples

### Presentation
- ✅ Full Slidev deck (~120 slides)
- ✅ Code examples and demos
- ✅ Interactive animations

## 🏗️ Mock Network Topology

```
spine1 (192.168.0.11) ──┬── leaf1 (192.168.0.21)
                        └── leaf2 (192.168.0.22)
spine2 (192.168.0.12) ──┘
```

**Built-in Scenarios:**
- ✅ BGP sessions up on spine1, spine2, leaf1
- ❌ leaf2 BGP session down (Idle state)
- ❌ leaf2 Ethernet3 interface down

Perfect for testing autonomous troubleshooting!

## 💡 Why Ollama?

### 100% Free
- No API keys required
- No usage limits
- No credit card
- No account signup

### Privacy & Control
- Runs entirely on your laptop
- No data sent to cloud
- Works offline
- Full control over models

### Production-Ready
- Same patterns work with any LLM
- Swap Ollama → OpenAI/Claude with 1 line
- Agent code stays identical

### Educational
- See how tool calling really works
- Understand LLM internals
- Debug locally
- No black boxes

## 🔧 Technical Stack

**Required (Free):**
- Python 3.10+
- Ollama (llama3.2:3b, ~2GB)
- Mock network devices (included)

**Optional:**
- llama3.1:8b for better quality (but slower)
- Claude/GPT for comparison (not needed)

**NOT Required:**
- ❌ API keys
- ❌ Cloud accounts
- ❌ Docker Desktop
- ❌ Virtual machines
- ❌ Network simulators

## 🎯 Learning Outcomes

By the end of this workshop, you will be able to:

1. **Explain LLM fundamentals** - How tokenization, attention, and sampling work
2. **Write production prompts** - Using RACE framework for consistent results
3. **Build stateful chatbots** - Managing conversation history and context
4. **Create autonomous agents** - Implementing tool calling with structured prompts
5. **Deploy to production** - Migration path from mock to real devices

## 📈 Workshop Flow

```
0:00 - Setup check (10 min)
0:10 - How LLMs work (20 min)
0:30 - Lab 1: Ollama (15 min)
0:45 - Prompt engineering (15 min)
1:00 - Lab 2: Prompts (25 min)
1:25 - LLM APIs (15 min)
1:40 - Lab 3: Chatbot (25 min)
2:05 - BREAK (10 min)
2:15 - Agentic patterns (20 min)
2:35 - Lab 4: Agents ⭐ (35 min)
3:10 - Production path (10 min)
3:20 - Wrap-up & Q&A (15 min)
```

## 🚀 Production Migration

### The Pattern

**Workshop (Mock Devices):**
```python
from examples.mock_network_devices import get_device_status

status = get_device_status("spine1")
# Returns: {"hostname": "spine1", "version": "4.28.0F", ...}
```

**Production (Your Network):**
```python
import paramiko

def get_device_status(device):
    ssh = paramiko.SSHClient()
    ssh.connect(device, username="admin", password=...)
    stdin, stdout, stderr = ssh.exec_command("show version | json")
    return json.loads(stdout.read())
```

**Your agent code doesn't change!** Just swap the backend function.

## 🎓 Who Should Attend

**Ideal for:**
- Network engineers learning AI automation
- DevOps/NetOps teams exploring AI
- Anyone automating network operations
- Python developers in networking

**Prerequisites:**
- Basic Python programming
- Understanding of networking (BGP, OSPF, SSH)
- Laptop with Python 3.10+

**NOT required:**
- AI/ML background
- Deep learning knowledge
- Paid API access
- Expensive hardware

## 📊 Success Metrics

**During Workshop:**
- 90%+ complete all labs
- Working chatbot by Lab 3
- Autonomous agent by Lab 4
- Understanding production path

**Post-Workshop:**
- 70%+ deploy to their networks
- 5+ custom implementations
- Active community engagement

## 🌟 Key Features

### Zero Cost
All labs use Ollama - **completely free forever**

### Zero Friction
15-minute setup, works on any laptop

### Production-Ready
Not toy examples - real patterns used in production

### Platform Agnostic
macOS, Linux, Windows all supported

### Privacy-First
All processing happens locally on your machine

## 📖 Documentation

- **[Quick Start](QUICKSTART.md)** - Get running in 5 minutes
- **[Setup Guide](docs/SETUP_GUIDE.md)** - Detailed installation
- **[Workshop Outline](docs/COMPLETE_WORKSHOP_OUTLINE.md)** - Full agenda
- **[Contributing](CONTRIBUTING.md)** - How to contribute

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style guide
- How to submit issues
- Pull request process
- Areas needing help

## 📜 License

MIT License - See [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Ollama** for making LLMs accessible and free
- **Meta** for Llama models
- **Network automation community** for inspiration
- **Workshop attendees** for feedback

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/sifbaksh/ai-networking-workshop/issues)
- **Discussions:** [GitHub Discussions](https://github.com/sifbaksh/ai-networking-workshop/discussions)
- **Email:** Contact via GitHub
- **Blog:** [sifbaksh.com](https://sifbaksh.com)

## 🗺️ Roadmap

**v1.0 (Current)**
- All 4 labs with Ollama
- Mock device simulator
- Complete documentation
- Slidev presentation

**v1.1 (Future)**
- Advanced multi-agent patterns
- Real device integration examples
- Video walkthroughs
- Community contributions

**v2.0 (Vision)**
- SOAR platform integration
- Observability patterns
- Multi-model support
- Advanced troubleshooting

---

## 🎉 Ready to Get Started?

```bash
# 1. Install Ollama
brew install ollama

# 2. Clone this repo
git clone https://github.com/sifbaksh/ai-networking-workshop.git
cd ai-networking-workshop

# 3. Install dependencies
pip3 install -r requirements.txt

# 4. Pull model
ollama pull llama3.2:3b

# 5. Run first lab
python3 labs/lab1-ollama/simple_ollama_test.py
```

**You're now building AI agents!** 🚀

---

**Workshop Date:** March 31, 2026  
**Created by:** Sif Baksh  
**License:** MIT  
**Cost:** $0 Forever
=======
# AI Network Automation MCP

A workshop-ready starter repo for building your first AI-powered network automation toolchain.

The goal is simple:

> Start with Python. Talk to real network devices. Use Claude to reason over network data. Use the RACE framework to keep the model grounded. Wrap the useful network functions as MCP tools.

This repo is designed for a PacketCoders-style workshop using Containerlab and Arista cEOS.

---

## What You Will Build

By the end of the first workshop, you will have:

1. A small Arista cEOS lab running in Containerlab.
2. Python scripts that connect to the devices and collect network state.
3. A Claude API example that analyzes network output using the RACE framework.
4. A read-only MCP server exposing network inspection tools.
5. A clear foundation for later videos: troubleshooting, pyATS parsing, NetBox intent checks, and safe change workflows.

---

## Repo Layout

```text
ai-network-automation-mcp/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── Makefile
├── lab/
│   ├── topology.clab.yml
│   └── configs/
│       ├── spine1.cfg
│       ├── leaf1.cfg
│       └── leaf2.cfg
├── scripts/
│   ├── 01_python_basics.py
│   ├── 02_inventory_loader.py
│   ├── 03_connect_to_device.py
│   ├── 04_get_interfaces.py
│   └── 05_claude_race_analysis.py
├── prompts/
│   ├── bad_prompt.txt
│   └── race_network_analysis_prompt.txt
├── mcp_server/
│   ├── server.py
│   ├── network_tools.py
│   └── inventory.yml
├── examples/
│   ├── interface_output.json
│   ├── bgp_output.json
│   └── claude_response_example.md
├── docs/
│   ├── episode-01-workshop-outline.md
│   ├── instructor-notes.md
│   └── mcp-client-config.md
└── tests/
    └── test_command_safety.py
```

---

## Prerequisites

You need:

- Docker
- Containerlab
- Python 3.10+
- Arista cEOS image imported into Docker
- Anthropic API key for the Claude example

Import your cEOS image into Docker using the tag referenced in `lab/topology.clab.yml`.

Example:

```bash
docker import cEOS64-lab-4.32.0F.tar.xz ceos:4.32.0F
```

---

## Setup

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy the environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:

```bash
ANTHROPIC_API_KEY=your_api_key_here
```

---

## Start the Lab

From the repo root:

```bash
containerlab deploy -t lab/topology.clab.yml
```

Confirm the containers are running:

```bash
docker ps
```

Destroy the lab when finished:

```bash
containerlab destroy -t lab/topology.clab.yml --cleanup
```

---

## Run the Python Examples

Start with the basics:

```bash
python scripts/01_python_basics.py
```

Load the device inventory:

```bash
python scripts/02_inventory_loader.py
```

Connect to a device:

```bash
python scripts/03_connect_to_device.py leaf1
```

Get interface status:

```bash
python scripts/04_get_interfaces.py leaf1
```

Analyze sample network output with Claude and RACE:

```bash
python scripts/05_claude_race_analysis.py examples/interface_output.json
```

---

## Run the MCP Server

Start the MCP server:

```bash
python mcp_server/server.py
```

By default, the server uses Streamable HTTP and listens on:

```text
http://localhost:8000/mcp
```

You can test it with MCP Inspector:

```bash
npx -y @modelcontextprotocol/inspector
```

Then connect to:

```text
http://localhost:8000/mcp
```

---

## MCP Tools Included

The first version exposes read-only tools:

| Tool | Purpose |
|---|---|
| `list_devices` | Show the devices in the lab inventory. |
| `get_device_facts` | Run `show version` against a selected device. |
| `check_interfaces` | Run `show interfaces status` against a selected device. |
| `run_safe_show_command` | Run approved read-only `show` commands. |

The point of episode one is not to make changes.

The point is to teach this path:

```text
Python function
↓
Network automation function
↓
Claude reasoning prompt
↓
MCP tool
↓
AI-assisted network operations
```

---

## Safety Boundary

This starter kit intentionally blocks configuration commands.

Allowed command style:

```text
show version
show interfaces status
show ip route
show ip bgp summary
```

Blocked command style:

```text
configure terminal
reload
copy
delete
write memory
bash
```

That makes the first workshop safer and easier to teach.


