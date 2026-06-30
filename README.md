# Building AI Agents for Network Operations

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/Ollama-local-brightgreen.svg)](https://ollama.com/)

Hands-on labs for building AI-powered network operations tools: local LLM prompts, prompt engineering, chatbots with memory, agentic tool calling, MCP tools, and production-readiness patterns.

The workshop is designed to run locally with Ollama and Python. Most labs use the included mock network devices, so you can learn the agent patterns without needing cloud API keys or a live network.

## Quick Start

### Prerequisites

- Python 3.10+
- Git
- Ollama
- Optional for live network labs: Docker, Containerlab, Arista cEOS image

Install Ollama on macOS:

```bash
brew install ollama
```

Or download it from [ollama.com/download](https://ollama.com/download).

### Setup

```bash
git clone https://github.com/PacktPublishing/Building-AI-Agents-for-Network-Operations.git
cd Building-AI-Agents-for-Network-Operations

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

ollama pull llama3.2:3b
ollama pull deepseek-r1:8b

python examples/test_setup.py
```

Model usage is split by chapter flow: `llama3.2:3b` is the baseline for the early prompt, parsing, and chatbot examples, while `deepseek-r1:8b` is used for the Lab 4 agentic workflow, including the Chapter 6 and Chapter 7 flow.

If Ollama is not already running:

```bash
ollama serve
```

Keep the virtual environment active while running the labs. If you open a new terminal, run:

```bash
source .venv/bin/activate
```

## Run the Labs

Run commands from the repo root unless a lab README says otherwise.

```bash
# Lab 1: Ollama basics and structured output
python labs/lab1-ollama/simple_ollama_test.py
python labs/lab1-ollama/json_output_challenge.py

# Lab 2: Prompt engineering with the RACE framework
python labs/lab2-prompts/prompt_engineering_race.py
python labs/lab2-prompts/netmiko_config_parser.py

# Lab 3: Chatbot patterns
python labs/lab3-chatbot/chatbot_v1_stateless.py
python labs/lab3-chatbot/chatbot_v2_with_memory.py

# Lab 4: Agentic network bot
python labs/lab4-agentic/agentic_network_bot_ollama.py

# Lab 5: MCP server and client examples
# First, test the tool layer
python labs/lab5-mcp/client_test.py

# Terminal 1: start the MCP server in SSE mode
python labs/lab5-mcp/mcp_server.py --sse

# Terminal 2: start the HTTP bridge
python labs/lab5-mcp/http_bridge.py

# Browser: open the UI
open labs/lab5-mcp/ui.html

# Lab 6: Production-readiness patterns
python labs/lab6-production-readiness/production_agent_skeleton.py
```

## Workshop Structure

### Lab 1: Ollama and Network Prompts

- Call local Ollama models from Python
- Control generation parameters
- Parse JSON output
- Practice error handling and model comparison

### Lab 2: Prompt Engineering

- Apply the RACE framework
- Build network analysis prompts
- Parse network configuration examples
- Reuse prompt templates from `labs/lab2-prompts/PROMPT_TEMPLATES.md`

### Lab 3: Network Chatbot

- Compare stateless and stateful chatbot behavior
- Add conversation memory
- Manage context for network troubleshooting
- Optional live SSH chatbot example

### Lab 4: Agentic Network Bot

- Define network inspection tools
- Let the agent call tools for device status, BGP, interfaces, topology, and safe show commands
- Troubleshoot the included mock spine-leaf network
- Optional Netmiko-backed live SSH version

### Lab 5: MCP

- Expose network tools through an MCP server
- Test the MCP client flow
- Use the simple HTTP bridge and browser UI examples

### Lab 6: Production Readiness

- Add safer tool boundaries
- Use production-oriented agent skeletons
- Review operational checklist items before real deployment

## Mock Network Topology

The mock network data lives in `examples/mock_network_devices.py`.

```text
spine1 (192.168.0.11) --+-- leaf1 (192.168.0.21)
                        +-- leaf2 (192.168.0.22)
spine2 (192.168.0.12) --+
```

Built-in scenarios:

- `spine1`, `spine2`, and `leaf1` have all BGP peers established.
- `leaf2` has one BGP neighbor in `Idle`.
- `leaf2` has `Ethernet3` down.

These scenarios are used by the chatbot and agent labs to demonstrate autonomous troubleshooting.

## Optional Live Network Lab

The `lab/` folder contains Containerlab assets:

```text
lab/
├── topology.clab.yml
└── configs/
    ├── leaf1.cfg
    ├── leaf2.cfg
    └── spine1.cfg
```

Deploy the lab when Docker, Containerlab, and the cEOS image are available:

```bash
containerlab deploy -t lab/topology.clab.yml
```

Destroy it when finished:

```bash
containerlab destroy -t lab/topology.clab.yml --cleanup
```

Live SSH examples include:

```bash
python scripts/03_connect_to_device.py leaf1
python scripts/04_get_interfaces.py leaf1
python labs/lab3-chatbot/chatbot_v3_live_ssh.py
python labs/lab4-agentic/lab4b_agentic_network_bot_netmiko.py
```

## Repository Layout

```text
Building-AI-Agents-for-Network-Operations/
├── README.md
├── QUICKSTART.md
├── requirements.txt
├── Makefile
├── .env.example
├── examples/
│   ├── mock_network_devices.py
│   ├── test_setup.py
│   ├── bgp_output.json
│   ├── interface_output.json
│   ├── temperature.py
│   └── tokens_test.py
├── lab/
│   ├── topology.clab.yml
│   └── configs/
├── labs/
│   ├── lab1-ollama/
│   ├── lab2-prompts/
│   ├── lab3-chatbot/
│   ├── lab4-agentic/
│   ├── lab5-mcp/
│   └── lab6-production-readiness/
├── prompts/
├── scripts/
├── tests/
└── bonus/
```

## Environment Variables

Copy the example environment file only if you are running examples that require external credentials:

```bash
cp .env.example .env
```

Most Ollama labs do not require `.env` values. External API examples and some live network examples may require credentials; check the relevant lab file or README before running them.

## Safety Boundary

The network examples are intentionally read-only by default. Safe command examples include:

```text
show version
show interfaces status
show ip route
show ip bgp summary
```

Unsafe configuration or destructive commands should remain blocked in production tool wrappers:

```text
configure terminal
reload
copy
delete
write memory
bash
```

## Troubleshooting

If imports fail, make sure the virtual environment is active and dependencies are installed:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If Ollama calls fail, confirm the service and models:

```bash
ollama serve
ollama list

# Labs 1-3: early prompt, parsing, and chatbot examples
ollama pull llama3.2:3b

# Lab 4: agentic workflow for Chapter 6 and Chapter 7
ollama pull deepseek-r1:8b
```

Run the setup check:

```bash
python examples/test_setup.py
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

MIT License. See [LICENSE](LICENSE).
