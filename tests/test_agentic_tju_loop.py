"""Offline protocol tests for Lab 4 native Function Calling."""

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "labs"
    / "lab4-agentic"
    / "agentic_network_bot.py"
)


def _load_agent_module():
    spec = importlib.util.spec_from_file_location("lab4_agentic_network_bot", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tool_result_keeps_matching_tool_call_id(monkeypatch):
    module = _load_agent_module()
    observed_messages = []

    def fake_chat_message(messages, **_kwargs):
        observed_messages.append(messages)
        if len(observed_messages) == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-test-1",
                        "type": "function",
                        "function": {
                            "name": "get_device_status",
                            "arguments": '{"device": "spine1"}',
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "spine1 is operational."}

    monkeypatch.setattr(module, "chat_message", fake_chat_message)
    result = module.AgenticNetworkBot().chat("Check spine1", verbose=False)

    assert result == "spine1 is operational."
    tool_message = observed_messages[1][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call-test-1"
