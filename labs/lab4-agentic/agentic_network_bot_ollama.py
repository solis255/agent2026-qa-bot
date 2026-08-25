#!/usr/bin/env python3
"""Backward-compatible launcher for the migrated Lab 4 agent.

The filename is retained so existing course commands and bookmarks still work.
The implementation now uses the TJU competition API and native Function
Calling; no local Ollama service or model download is required.
"""

from agentic_network_bot import (
    AgenticNetworkBot,
    challenge_1,
    challenge_2,
    challenge_3,
    demo_multi_device_query,
    demo_simple_query,
    demo_topology_analysis,
    demo_troubleshooting,
    interactive_mode,
)

__all__ = [
    "AgenticNetworkBot",
    "challenge_1",
    "challenge_2",
    "challenge_3",
    "demo_multi_device_query",
    "demo_simple_query",
    "demo_topology_analysis",
    "demo_troubleshooting",
    "interactive_mode",
]


if __name__ == "__main__":
    print("Lab 4 compatibility launcher: TJU DeepSeek API + native Function Calling")
    demo_simple_query()
