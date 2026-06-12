#!/usr/bin/env python3
"""
Analyze network data with Claude using the RACE framework.

RACE
  R - Role
  A - Anchors
  C - Context
  E - Expected output
"""

import argparse
import os
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from rich import print

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPT_FILE = REPO_ROOT / "prompts" / "pene_network_analysis_prompt.txt"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def analyze_network_output(input_file: Path) -> str:
    load_dotenv(REPO_ROOT / ".env")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "replace_me":
        raise RuntimeError("Set ANTHROPIC_API_KEY in your .env file first.")

    model = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
    client = Anthropic(api_key=api_key)

    system_prompt = read_file(PROMPT_FILE)
    network_data = read_file(input_file)

    message = client.messages.create(
        model=model,
        max_tokens=1200,
        temperature=0.2,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Analyze this network data:\n\n{network_data}",
            }
        ],
    )

    return "\n".join(block.text for block in message.content if block.type == "text")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze network output with Claude and RACE")
    parser.add_argument("input_file", help="Path to a network output file, for example examples/interface_output.json")
    args = parser.parse_args()

    input_file = Path(args.input_file)
    if not input_file.exists():
        print(f"[red]File not found:[/red] {input_file}")
        return 1

    try:
        response = analyze_network_output(input_file)
    except Exception as exc:
        print(f"[red]Error:[/red] {exc}")
        return 1

    print(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
