import sys
from pathlib import Path


LAB5_DIR = Path(__file__).resolve().parents[1] / "labs" / "lab5-mcp"
if str(LAB5_DIR) not in sys.path:
    sys.path.insert(0, str(LAB5_DIR))

from network_tools import safe_show_command  # noqa: E402


def test_allows_show_commands():
    result = safe_show_command("spine1", "show version")

    assert result["device"] == "spine1"
    assert result["command"] == "show version"
    assert result["mode"] == "read_only_mock"
    assert "error" not in result


def test_blocks_non_show_commands():
    result = safe_show_command("spine1", "configure terminal")

    assert result["error"] == "Only read-only show commands are allowed in this lab"
    assert result["blocked_command"] == "configure terminal"


def test_rejects_unknown_device_before_running_command():
    result = safe_show_command("unknown", "show version")

    assert "not in the workshop topology" in result["error"]
    assert result["available_devices"] == ["spine1", "spine2", "leaf1", "leaf2"]
