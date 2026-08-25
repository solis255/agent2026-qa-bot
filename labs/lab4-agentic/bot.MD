# Lab 4 Implementation Notes

The active implementation is `agentic_network_bot.py`. It reuses `examples/tju_llm_client.py`, so endpoint validation, authentication, retries, token reporting, and API errors are consistent with Labs 1–3.

## Where to modify behavior

| Goal | Location |
|---|---|
| Add or remove a tool | `AgenticNetworkBot.tools` and `AgenticNetworkBot.tools_map` |
| Change agent policy | `AgenticNetworkBot.system_prompt` |
| Change the tool loop | `AgenticNetworkBot.chat()` |
| Change API parameters | `AgenticNetworkBot._call_tju()` |
| Change mock outputs | `examples/mock_network_devices.py` |
| Use real devices | `lab4b_agentic_network_bot_netmiko.py` |

Every tool schema must use JSON Schema and match the Python callable's parameters. Every returned tool message must include the ID of the call it answers. Unknown tools and invalid arguments are returned to the model as controlled error dictionaries.

The default loop cap is six rounds. Increase it only with a clear token budget and operational reason because each round consumes an additional API request.

## Configuration

The root `.env` supplies:

```dotenv
TJU_API_KEY=your-key
TJU_API_BASE=https://ai.tju.edu.cn/api/agent2026/your-exclusive-address
TJU_MODEL=tju-llm
TJU_SHOW_TOKEN_USAGE=true
```

The base address must not end with `/chat/completions`. No local model download is required.
