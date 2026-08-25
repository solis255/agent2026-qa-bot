# Windows Quick Start Guide

Labs 1–4 now use the school's TJU competition API through its OpenAI-compatible interface. Labs 5–6 do not call an LLM directly. You do **not** need to install Ollama or download local models.

## 1. Prepare Python

Install Python 3.10 or newer and Git, then open PowerShell:

```powershell
git clone https://github.com/PacktPublishing/Building-AI-Agents-for-Network-Operations
cd Building-AI-Agents-for-Network-Operations
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If this project is already cloned, start at `cd` and create/activate the virtual environment.

## 2. Configure the TJU API

Create the private configuration file once:

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in these values:

```dotenv
TJU_API_KEY=replace-with-your-real-api-key
TJU_API_BASE=https://ai.tju.edu.cn/api/agent2026/your-exclusive-address
TJU_MODEL=tju-llm
TJU_SHOW_TOKEN_USAGE=true
```

Put your API Key only after `TJU_API_KEY=` in the project-root `.env`. Do not add `/chat/completions` to `TJU_API_BASE`; the SDK adds it automatically. `.env` is ignored by Git.

Validate the local configuration without using tokens, then perform one live request if desired:

```powershell
python examples\test_setup.py
python scripts\test_tju_api.py
```

## 3. Run Labs 1–6

Run commands from the project root while `.venv` is active:

```powershell
# Lab 1: API calls, structured output, and parsing
python labs\lab1-ollama\simple_ollama_test.py

# Lab 2: RACE prompt engineering
python labs\lab2-prompts\prompt_engineering_race.py

# Lab 3: chatbot memory
python labs\lab3-chatbot\chatbot_v2_with_memory.py

# Lab 4: native Function Calling over the TJU API
python labs\lab4-agentic\agentic_network_bot.py

# Lab 5: MCP client test (no direct LLM call)
python labs\lab5-mcp\client_test.py

# Lab 6: production-readiness examples (no direct LLM call)
python labs\lab6-production-readiness\safe_tools.py
python labs\lab6-production-readiness\production_agent_skeleton.py
```

The names `lab1-ollama` and `agentic_network_bot_ollama.py` are retained only for compatibility with the original course paths. Their current implementations use the TJU API.

## Troubleshooting

- `401`: check `TJU_API_KEY` in `.env`; remove surrounding quotes and spaces.
- `429`: wait and retry; the competition platform is rate-limiting requests.
- Address error: copy the exclusive base address from the competition platform and omit `/chat/completions`.
- Import error: reactivate `.venv`, then run `python -m pip install -r requirements.txt`.
- Token display: set `TJU_SHOW_TOKEN_USAGE=true`; set it to `false` to hide usage output.

Lab 4 may execute several model rounds because every tool result is sent back to the model. A six-round safety cap prevents an unbounded loop.
