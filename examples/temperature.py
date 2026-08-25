#!/usr/bin/env python3
"""Demonstrate temperature using the shared TJU API client."""

from tju_llm_client import TJUAPIError, generate_text


def main() -> None:
    prompt = "Generate a BGP configuration for AS 65001 with neighbor 10.0.0.1"
    try:
        print(generate_text(prompt, temperature=1.5, max_tokens=200))
    except TJUAPIError as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
