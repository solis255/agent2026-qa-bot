#!/usr/bin/env python3
"""Load the lab inventory from YAML."""

from pathlib import Path
from typing import Any

import yaml
from rich import print

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_FILE = REPO_ROOT / "mcp_server" / "inventory.yml"


def load_inventory() -> dict[str, Any]:
    with INVENTORY_FILE.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def main() -> None:
    inventory = load_inventory()
    print("[bold]Loaded inventory[/bold]")
    for name, device in inventory["devices"].items():
        print(f"- {name}: {device['host']} ({device['device_type']})")


if __name__ == "__main__":
    main()
