# Lab 3B: Stateful Chatbot with Memory

`chatbot_v2_with_memory.py` stores every user and assistant turn in `conversation_history`. On each request it sends a standard message list containing the system prompt and full history to the TJU competition API.

## Run on Windows

```powershell
python labs\lab3-chatbot\chatbot_v2_with_memory.py
```

Interactive commands:

- `reset`: clear application-managed memory.
- `quit`: exit.

Important methods:

- `NetworkChatbot.chat()`: appends the user message, calls `chat_message()`, then stores the assistant response.
- `NetworkChatbot.reset()`: clears history.
- `NetworkChatbot.get_history_length()`: reports stored message count.
- `_build_prompt()`: retained as a learning aid; the migrated runtime sends native role-based messages instead of a concatenated prompt.

Memory belongs to the application, not to the model service. Longer histories also consume more input tokens.
