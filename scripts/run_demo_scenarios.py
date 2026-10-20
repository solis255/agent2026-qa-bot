"""Offline acceptance through the real ASGI app; writes only a temporary database."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=["all", "dns_recovery", "dns_escalation", "vpn_proxy", "vpn_unknown", "single_service", "recurrence"], default="all")
    args = parser.parse_args(argv)
    # Avoid the imported application's default on-disk history and RAG loader.
    os.environ["DIAGNOSIS_HISTORY_ENABLED"] = "false"
    os.environ["RAG_ENABLED"] = "false"
    from fastapi.testclient import TestClient
    from netpilot.main import create_app
    from netpilot.config import Settings
    from netpilot.demo.scenarios import SCENARIOS
    from netpilot.demo.acceptance import checked, run_scenario
    with TemporaryDirectory(prefix="netpilot-demo-") as tmp:
        app = create_app(Settings(_env_file=None, demo_mode=True, tju_api_key=None, tool_mode="mock",
            rag_enabled=False, diagnosis_history_enabled=True, diagnosis_db_path=Path(tmp) / "acceptance.db"))
        with TestClient(app) as client:
            checked(client.post("/api/auth/register", json={"username": "demo_" + uuid4().hex[:16], "password": uuid4().hex}))
            for key in SCENARIOS if args.scenario == "all" else [args.scenario]:
                print(f"[Demo] {SCENARIOS[key].title}")
                try:
                    result = run_scenario(client, key, emit=lambda message: print("  [OK] " + message))
                    print("  Metrics: " + str(result["status"]["metrics"]))
                    print("PASS")
                except Exception as exc:
                    print(f"FAIL ({type(exc).__name__}): {exc}", file=sys.stderr)
                    return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
