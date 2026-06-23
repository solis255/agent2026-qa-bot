.PHONY: setup lab-up lab-down basics inventory version interfaces claude mcp test

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

lab-up:
	containerlab deploy -t lab/topology.clab.yml

lab-down:
	containerlab destroy -t lab/topology.clab.yml --cleanup

basics:
	python scripts/01_python_basics.py

inventory:
	python scripts/02_inventory_loader.py

version:
	python scripts/03_connect_to_device.py leaf1

interfaces:
	python scripts/04_get_interfaces.py leaf1

claude:
	python scripts/05_claude_race_analysis.py examples/interface_output.json

mcp:
	python mcp_server/server.py

test:
	pytest -q
