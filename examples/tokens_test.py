#!/usr/bin/env python3
"""
Example: inspect Ollama prompt token usage.

This uses the same requests-based Ollama API pattern as the early labs. It is
kept under an executable guard so pytest can import the file without making a
local model call.
"""

from __future__ import annotations


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:3b"


def count_prompt_tokens(prompt: str, model: str = MODEL) -> int:
    """Return the prompt token count reported by Ollama."""
    import requests

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=60,
    )
    response.raise_for_status()
    return int(response.json().get("prompt_eval_count", 0))


def main() -> None:
    import requests

    text = """
router bgp 65001
 neighbor 10.0.0.1 remote-as 65002
 neighbor 10.0.0.1 description CORE-RTR-01
""".strip()

    try:
        tokens = count_prompt_tokens(text)
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to Ollama. Is it running? Try: ollama serve")
        return
    except requests.exceptions.HTTPError as exc:
        print(f"Error: Ollama request failed: {exc}")
        print(f"Check that the model is installed: ollama pull {MODEL}")
        return

    print(f"Tokens: {tokens}")


if __name__ == "__main__":
    main()
