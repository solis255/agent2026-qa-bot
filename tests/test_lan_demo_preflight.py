"""Safety and truthfulness checks for the read-only LAN demo preflight."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from netpilot.config import Settings


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_lan_demo.py"
SPEC = importlib.util.spec_from_file_location("check_lan_demo", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _demo_settings(tmp_path: Path, **overrides: object) -> Settings:
    index = tmp_path / "index"
    index.mkdir(exist_ok=True)
    for name in ("vectors.faiss", "chunks.json", "manifest.json"):
        (index / name).touch()
    values = {
        "tju_api_key": "preflight-secret-not-for-output",
        "tool_mode": "mock",
        "scenario_switch_enabled": True,
        "diagnosis_history_enabled": True,
        "app_host": "0.0.0.0",
        "auth_cookie_secure": False,
        "debug": False,
        "rag_enabled": True,
        "rag_index_dir": index,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_lan_demo_preflight_accepts_complete_safe_demo_settings(tmp_path: Path) -> None:
    checks = MODULE.assess(_demo_settings(tmp_path))
    assert checks and all(item.ready for item in checks)
    assert "preflight-secret-not-for-output" not in repr(checks)


@pytest.mark.parametrize(
    ("overrides", "label"),
    [
        ({"tju_api_key": None}, "Model key configured"),
        ({"tool_mode": "local"}, "Mock Provider"),
        ({"scenario_switch_enabled": False}, "Scenario switching"),
        ({"diagnosis_history_enabled": False}, "Diagnosis history"),
        ({"app_host": "127.0.0.1"}, "Trusted LAN bind"),
        ({"auth_cookie_secure": True}, "HTTP cookie compatible"),
        ({"debug": True}, "Debug disabled"),
        ({"rag_enabled": False}, "RAG enabled"),
    ],
)
def test_lan_demo_preflight_flags_incomplete_settings(
    tmp_path: Path, overrides: dict[str, object], label: str
) -> None:
    checks = MODULE.assess(_demo_settings(tmp_path, **overrides))
    assert label in {item.label for item in checks if not item.ready}


def test_lan_demo_preflight_requires_rag_files(tmp_path: Path) -> None:
    settings = _demo_settings(tmp_path)
    (settings.rag_index_dir / "manifest.json").unlink()
    checks = MODULE.assess(settings)
    assert "Local RAG index files" in {item.label for item in checks if not item.ready}


def test_lan_bind_accepts_private_ipv4_not_public_or_loopback() -> None:
    assert MODULE._lan_bind("192.168.10.8")
    assert MODULE._lan_bind("10.1.2.3")
    assert MODULE._lan_bind("172.16.0.1")
    assert MODULE._lan_bind("0.0.0.0")
    assert not MODULE._lan_bind("8.8.8.8")
    assert not MODULE._lan_bind("169.254.1.2")
    assert not MODULE._lan_bind("127.0.0.1")


def test_auth_cannot_be_disabled_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "false")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_preflight_does_not_echo_invalid_configuration_value(tmp_path: Path) -> None:
    secret = "do-not-print-this-invalid-value"
    environment = os.environ.copy()
    environment.update({"AUTH_ENABLED": secret, "PYTHONPATH": str(ROOT / "src")})
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert secret not in result.stdout + result.stderr
