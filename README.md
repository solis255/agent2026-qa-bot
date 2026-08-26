# Building AI Agents for Network Operations

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![TJU API](https://img.shields.io/badge/LLM-TJU_API-brightgreen.svg)](https://agent2026.tju.edu.cn/)

Hands-on labs for building AI-powered network operations tools: LLM prompts, prompt engineering, chatbots with memory, agentic tool calling, MCP tools, and production-readiness patterns.

Labs 1–4 use the school's OpenAI-compatible TJU competition API. Labs 5–6 do not call an LLM directly. Most labs use included mock network devices, so no live network is required.


## Book chapter and lab map

The following table shows where each chapter connects to the repository files. Some chapters are conceptual, while others use hands-on lab folders or reusable templates.

| Chapter | Main repository files |
|---|---|
| Chapter 1: Understanding AI Agents for Network Operations | Conceptual chapter; no lab required |
| Chapter 2: LLM Fundamentals and Local Setup | `QUICKSTART.md`, `examples/temperature.py`, `labs/lab1-ollama/` |
| Chapter 3: Prompt Engineering for Network Automation | `labs/lab2-prompts/`, `prompts/` |
| Chapter 4: Parsing Network Outputs into Structured Data | `labs/lab1-ollama/challenge_*.py`, `examples/interface_output.json`, `examples/bgp_output.json` |
| Chapter 5: Building a Network Chatbot with Memory | `labs/lab3-chatbot/` |
| Chapter 6: Designing Tools and Agentic Workflows | `labs/lab4-agentic/agentic_network_bot_ollama.py`, `examples/mock_network_devices.py` |
| Chapter 7: Building the Main Network Troubleshooting Agent | `labs/lab4-agentic/agentic_network_bot_ollama.py`, `examples/mock_network_devices.py` |
| Chapter 8: From Lab Agents to Reusable Tools with MCP | `labs/lab5-mcp/` |
| Chapter 9: Moving Toward Production-Ready Network Agents | `labs/lab6-production-readiness/` |
| Appendix A: AI Network Agent Design Toolkit | `docs/design-toolkit/` |

Ready-to-copy versions of the Appendix A worksheets and templates are available in `docs/design-toolkit/`.

## Quick Start

### Prerequisites

- Python 3.10+
- Git
- TJU competition API Key and exclusive base address
- Optional for live network labs: Docker, Containerlab, Arista cEOS image

### Setup

```bash
git clone https://github.com/PacktPublishing/Building-AI-Agents-for-Network-Operations.git
cd Building-AI-Agents-for-Network-Operations

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .

cp .env.example .env
# Edit .env and fill TJU_API_KEY plus the competition platform's exclusive TJU_API_BASE.
python examples/test_setup.py
python scripts/test_tju_api.py
```

The configured model name is `tju-llm`. The old `lab1-ollama` directory and `agentic_network_bot_ollama.py` filename remain only to preserve existing course links; their implementations now call the TJU API. Windows users should follow [QUICKSTART.md](QUICKSTART.md).

Keep the virtual environment active while running the labs. If you open a new terminal, run:

```bash
source .venv/bin/activate
```

Windows PowerShell users should activate the repository environment explicitly:

```powershell
.\.venv\Scripts\Activate.ps1
```

This avoids accidentally running the project with another system or Anaconda Python installation.

## TJU NetPilot Application

`src/netpilot/` is the formal product entry point for TJU NetPilot. It is separate from the preserved teaching labs and provides the validated application shell, static Chinese Web UI, public health endpoint, the Milestone 2 read-only network Tool layer, and the Milestone 3 production TJU ordinary-chat client.

Start the application from the repository root:

```bash
python -m uvicorn netpilot.main:app --reload
```

Then open <http://127.0.0.1:8000/>. Service readiness is available at <http://127.0.0.1:8000/api/health>:

```json
{
  "status": "ok",
  "llm_configured": true,
  "tool_mode": "mock",
  "rag_ready": false
}
```

The application deliberately starts when `TJU_API_KEY` is absent and reports `llm_configured: false`. Creating the configured `TJUClient` does not send a network request; the isolated live check below performs the first call. `rag_ready` remains false until the RAG milestone initializes a usable retriever. No health response exposes credentials.

### Network Tool Providers

NetPilot creates one provider from `TOOL_MODE` when the FastAPI application starts. Provider construction performs no network request.

- `TOOL_MODE=mock` is deterministic and fully offline. It supports `healthy`, `dns_failure`, `gateway_unreachable`, `tcp_ssh_blocked`, `http_failure`, and `partial_connectivity`.
- `TOOL_MODE=local` runs bounded, read-only checks against the machine hosting NetPilot. It supports Windows, Linux, and macOS with graceful degradation when a system traceroute command is unavailable.

Both providers expose the same six tools:

```text
get_network_info
ping_host
dns_lookup
tcp_check
http_check
traceroute
```

Every call returns a structured `ToolResult` containing `success`, `tool`, `summary`, `data`, `error`, and `duration_ms`. `success` means that the tool produced diagnostic evidence; a valid negative observation such as `reachable=false` remains successful evidence. Invalid input, unavailable executables, and unexpected execution failures return `success=false` with a stable error code.

The HTTP tool accepts only HTTP(S), validates each redirect, blocks localhost, metadata, internal, private, loopback, and link-local targets, limits redirects and response headers, and streams only response metadata instead of downloading content. System tools always use fixed argument lists, `shell=False`, output caps, and timeouts.

Milestone 2 tests are fully offline by default:

```bash
python -m pytest tests/test_tools.py -q
python -m pytest tests/test_mock_scenarios.py -q
python -m pytest tests/test_tool_security.py -q
python -m pytest -q
```

## Run the Labs

Run commands from the repo root unless a lab README says otherwise.

```bash
# Lab 1: TJU API basics and structured output
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

## Lab Structure

### Lab 1: TJU API and Network Prompts

- Call the configured competition model from Python
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
├── pyproject.toml
├── Makefile
├── .env.example
├── src/
│   └── netpilot/
│       ├── api/
│       ├── models/
│       ├── tools/
│       ├── config.py
│       └── main.py
├── web/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── favicon.svg
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
├── docs/
│   └── design-toolkit/
├── scripts/
├── tests/
└── bonus/
```

## Environment Variables

Create the private environment file before running Labs 1–4:

```bash
cp .env.example .env
```

Fill `TJU_API_KEY`, `TJU_API_BASE`, and `TJU_MODEL=tju-llm`. Do not append `/chat/completions` to the base address. `TJU_TIMEOUT_SECONDS` defaults to 60 and `TJU_MAX_RETRIES` defaults to 2 bounded SDK retries. NetPilot also reads the Agent, Tool, RAG, and App variables documented in `.env.example`. `.env` is ignored by Git and the API Key must never be committed or returned by an API.

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
python -m pip install -e .
```

If an API call fails, validate configuration and then make one live test request:

```bash
python examples/test_setup.py
python scripts/test_tju_api.py
```

HTTP 401 indicates an API Key problem; HTTP 429 indicates rate limiting. See [QUICKSTART.md](QUICKSTART.md) for Windows-specific commands.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

MIT License. See [LICENSE](LICENSE).
