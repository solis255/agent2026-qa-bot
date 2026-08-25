# Lab 3A: Stateless Chatbot

`chatbot_v1_stateless.py` demonstrates that separate Chat Completions requests do not share memory. Each call sends only the latest user message through `examples/tju_llm_client.py`.

## Run on Windows

From the project root with `.venv` active and `.env` configured:

```powershell
python labs\lab3-chatbot\chatbot_v1_stateless.py
```

The second question asks what the user previously asked. Because the first turn is not resent, the model cannot reliably answer. This is intentional and motivates Part B.

Relevant code locations:

- `simple_chat()`: one independent API call.
- `examples/tju_llm_client.py`: credentials, endpoint, retries, errors, and token reporting.

No local model download or model service is needed.
