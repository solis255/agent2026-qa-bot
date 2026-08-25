#!/usr/bin/env python3
"""Inspect prompt token usage reported by the TJU competition API."""

from tju_llm_client import DEFAULT_MODEL, TJUAPIError, generate_text_result


def count_prompt_tokens(prompt: str, model: str = DEFAULT_MODEL) -> int:
    """Send one short completion and return its reported prompt-token count."""
    result = generate_text_result(prompt, model=model, max_tokens=1)
    return int(result["tokens"]["prompt"])


def main() -> None:
    text = """
router bgp 65001
 neighbor 10.0.0.1 remote-as 65002
 neighbor 10.0.0.1 description CORE-RTR-01
""".strip()
    try:
        print(f"Prompt tokens: {count_prompt_tokens(text)}")
    except TJUAPIError as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
