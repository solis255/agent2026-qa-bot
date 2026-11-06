from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    "ST-CONTRACT", "ST-ELEMENTS", "ST-DEFAULT", "ST-DRAWER", "ST-ESC",
    "ST-ENVIRONMENT", "ST-TARGET", "ST-SNAPSHOT", "ST-CONTEXT", "ST-CHECK",
    "ST-RECHECK", "ST-STALE-ACTION", "ST-PLAN", "ST-VERIFICATION", "ST-RESOLUTION",
    "ST-ESCALATION", "ST-HISTORY-RETURN", "ST-HISTORY-GUARDS", "ST-HISTORY-PAGING",
    "ST-HISTORY-SWITCH", "ST-HISTORY-RACE", "ST-DEMO", "ST-RESET", "ST-STYLE",
]


@pytest.mark.parametrize("case", CASES)
def test_student_ui_contract_and_interaction(case):
    node = shutil.which("node")
    if not node or not (ROOT / "web/node_modules/jsdom/package.json").is_file():
        pytest.skip("requires Node.js and web npm ci")
    result = subprocess.run(
        [node, str(ROOT / "tests/web_student_ui_runtime.cjs"), case], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
