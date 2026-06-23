# Book-to-Repo Map

This document maps the proposed book, **AI Agents for Network Operations**, to the workshop repository.

Use it as a planning guide for keeping the book chapters, workshop labs, and supporting assets aligned.

## Quick alignment summary

| Book chapter | Repo location | Alignment |
|---|---|---|
| Chapter 1: Understanding AI agents for network operations | `README.md`, `docs/COMPLETE_WORKSHOP_OUTLINE.md` | Strong |
| Chapter 2: LLM fundamentals and local setup | `labs/lab1-ollama/`, `docs/SETUP_GUIDE.md`, `QUICKSTART.md` | Strong |
| Chapter 3: Prompt engineering for network automation | `labs/lab2-prompts/` | Strong |
| Chapter 4: Parsing network outputs into structured data | `labs/lab1-ollama/`, `labs/lab2-prompts/`, `examples/mock_network_devices.py` | Strong, with room for more examples |
| Chapter 5: Building a network chatbot with memory | `labs/lab3-chatbot/` | Strong |
| Chapter 6: Designing tools and agentic workflows | `labs/lab4-agentic/` | Strong |
| Chapter 7: Building the main network troubleshooting agent | `labs/lab4-agentic/`, `examples/mock_network_devices.py` | Strong |
| Chapter 8: From lab agents to reusable tools with MCP | `labs/lab5-mcp/` | Added |
| Chapter 9: Moving toward production ready network agents | `labs/lab6-production-readiness/` | Added |
| Appendix: Setup help, glossary, and checklists | `docs/`, `labs/lab6-production-readiness/production_checklist.md` | Partial |

## Chapter-by-chapter mapping

### Chapter 1: Understanding AI agents for network operations

**Primary repo assets**

- `README.md`
- `docs/COMPLETE_WORKSHOP_OUTLINE.md`

**What the repo already supports**

- Why this workshop focuses on building AI agents instead of only using AI tools.
- The difference between chatbots, copilots, scripts, and agents.
- The workshop progression from local LLM calls to agentic troubleshooting.

**Recommended additions**

- Add a short diagram that shows the difference between script, chatbot, copilot, and agent.
- Add a use case decision matrix: deterministic automation vs. LLM-assisted workflow vs. agentic workflow.

### Chapter 2: LLM fundamentals and local setup

**Primary repo assets**

- `labs/lab1-ollama/`
- `docs/SETUP_GUIDE.md`
- `QUICKSTART.md`
- `examples/test_setup.py`

**What the repo already supports**

- Ollama setup.
- Local model pull.
- First Python call to an LLM.
- Structured JSON output practice.
- Basic troubleshooting for setup issues.

**Recommended additions**

- Add a small token/context demonstration script.
- Add a comparison note for `llama3.2:3b` vs. larger local models.

### Chapter 3: Prompt engineering for network automation

**Primary repo assets**

- `labs/lab2-prompts/prompt_engineering_race.py`
- `labs/lab2-prompts/PROMPT_TEMPLATES.md`

**What the repo already supports**

- RACE prompt framework.
- Before/after prompt examples.
- Config parsing.
- Alert triage.
- Documentation and structured output examples.

**Recommended additions**

- Add more messy-data examples.
- Add a prompt scoring worksheet.
- Add expected outputs for each prompt challenge.

### Chapter 4: Parsing network outputs into structured data

**Primary repo assets**

- `labs/lab1-ollama/`
- `labs/lab2-prompts/`
- `examples/mock_network_devices.py`

**What the repo already supports**

- Interface output parsing.
- JSON output challenge.
- Mock command outputs for BGP, interfaces, and device version.
- Structured summaries that can feed later agent tools.

**Recommended additions**

- Add a dedicated `parsing_examples/` subfolder.
- Add schemas for interface, BGP, device, and topology outputs.
- Add validation examples with intentionally malformed LLM output.

### Chapter 5: Building a network chatbot with memory

**Primary repo assets**

- `labs/lab3-chatbot/chatbot_v1_stateless.py`
- `labs/lab3-chatbot/chatbot_v2_with_memory.py`

**What the repo already supports**

- Stateless chatbot behavior.
- Conversation history.
- System prompts.
- Context handling.
- Memory as application state.

**Recommended additions**

- Add a conversation summarization example.
- Add save/reload memory example if not already present.
- Add exercises around context window limits.

### Chapter 6: Designing tools and agentic workflows

**Primary repo assets**

- `labs/lab4-agentic/`
- `examples/mock_network_devices.py`

**What the repo already supports**

- Tool definitions.
- Tool calling.
- Multi-step investigation.
- Agentic troubleshooting loop.
- Read-only mock device interactions.

**Recommended additions**

- Add a tool design checklist.
- Add examples of bad tool descriptions and improved tool descriptions.
- Add a small trace example that shows observe, reason, act, and report.

### Chapter 7: Building the main network troubleshooting agent

**Primary repo assets**

- `labs/lab4-agentic/agentic_network_bot_ollama.py`
- `examples/mock_network_devices.py`

**What the repo already supports**

- Complete mock topology.
- Spine-leaf troubleshooting.
- BGP state checks.
- Interface checks.
- Reachability checks.
- Evidence-based final answer generation.

**Recommended additions**

- Add scenario files for each troubleshooting case.
- Add expected investigation paths.
- Add a rubric for evaluating the final agent response.

### Chapter 8: From lab agents to reusable tools with MCP

**Primary repo assets**

- `labs/lab5-mcp/README.md`
- `labs/lab5-mcp/network_tools.py`
- `labs/lab5-mcp/mcp_server.py`
- `labs/lab5-mcp/client_test.py`

**What the repo now supports**

- MCP packaging pattern.
- Reuse of Lab 4 network tools.
- MCP server with read-only network tools.
- Safe command filtering.
- Local sanity test before client integration.

**Recommended additions**

- Add screenshots or examples from an MCP-capable client.
- Add an MCP troubleshooting guide.
- Add a second MCP server example for another system such as NetBox.

### Chapter 9: Moving toward production ready network agents

**Primary repo assets**

- `labs/lab6-production-readiness/README.md`
- `labs/lab6-production-readiness/safe_tools.py`
- `labs/lab6-production-readiness/production_agent_skeleton.py`
- `labs/lab6-production-readiness/production_checklist.md`

**What the repo now supports**

- Read-only-first design.
- Device and command allowlists.
- Structured audit logging.
- Mock-to-real backend abstraction.
- Production readiness checklist.
- Human approval and blast-radius discussion.

**Recommended additions**

- Add a Netmiko backend example for lab-only devices.
- Add Containerlab and Arista cEOS example assets.
- Add JSONL audit logging to disk.
- Add a small observability dashboard or metrics example.

### Appendix: Setup help, glossary, and checklists

**Primary repo assets**

- `docs/SETUP_GUIDE.md`
- `docs/TROUBLESHOOTING.md`
- `labs/lab6-production-readiness/production_checklist.md`

**Recommended additions**

- `docs/glossary.md`
- `docs/prompt-checklist.md`
- `docs/tool-design-checklist.md`
- `docs/lab-file-map.md`

## Suggested repo roadmap

### Near-term

- Update the main `README.md` to reference Lab 5 and Lab 6.
- Add optional MCP dependency notes.
- Add chapter asset placeholders under `docs/chapter-assets/`.

### Mid-term

- Add dedicated parsing schemas for Chapter 4.
- Add scenario files for Chapter 7.
- Add MCP client screenshots or short walkthroughs.

### Later

- Add Containerlab/cEOS production-style examples.
- Add NetBox, pyATS, or Netmiko backend examples.
- Add a CI check that runs all mock-based examples.
