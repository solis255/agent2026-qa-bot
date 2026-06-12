# Chapter Assets

This folder holds supporting assets for the book **AI Agents for Network Operations**.

Use this folder for diagrams, worksheets, checklists, scenario files, and chapter-specific supporting material that should travel with the workshop repo.

## Suggested structure

```text
docs/chapter-assets/
├── README.md
├── chapter-01-agent-types/
├── chapter-02-local-llm-setup/
├── chapter-03-pene-prompts/
├── chapter-04-structured-parsing/
├── chapter-05-chatbot-memory/
├── chapter-06-tool-calling/
├── chapter-07-troubleshooting-agent/
├── chapter-08-mcp-tools/
└── chapter-09-production-readiness/
```

## Asset ideas by chapter

### Chapter 1: Understanding AI agents for network operations

- Agent vs. chatbot vs. copilot diagram
- Use case decision matrix
- NetOps pain point worksheet

### Chapter 2: LLM fundamentals and local setup

- Token/context window diagram
- Ollama setup screenshots
- Local model comparison notes

### Chapter 3: Prompt engineering for network automation

- RACE worksheet
- Prompt scorecard
- Before/after prompt examples

### Chapter 4: Parsing network outputs into structured data

- JSON schema examples
- Messy CLI output samples
- Validation failure examples

### Chapter 5: Building a network chatbot with memory

- Stateless vs. stateful flow diagram
- Conversation memory diagram
- Context summarization worksheet

### Chapter 6: Designing tools and agentic workflows

- Tool design checklist
- Agentic loop diagram
- Tool trace examples

### Chapter 7: Building the main network troubleshooting agent

- Troubleshooting scenarios
- Expected investigation paths
- Agent response rubric

### Chapter 8: From lab agents to reusable tools with MCP

- MCP architecture diagram
- MCP client configuration examples
- Tool reuse worksheet

### Chapter 9: Moving toward production ready network agents

- Read-only-first maturity model
- Approval workflow diagram
- Production readiness worksheet

## Naming convention

Use clear, chapter-aligned names:

```text
chapter-03-pene-prompts/pene-worksheet.md
chapter-07-troubleshooting-agent/bgp-down-scenario.md
chapter-09-production-readiness/read-only-first-maturity-model.md
```

Keep assets lightweight and editable where possible. Prefer Markdown, Mermaid diagrams, JSON examples, and plain text scenario files before adding binary images.
