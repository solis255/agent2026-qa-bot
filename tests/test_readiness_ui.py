from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case",["READY-WINDOWS","READY-UNSUPPORTED","READY-UNKNOWN-RESET"])
def test_collector_guide_obeys_server_platform_decision(case):
    node=shutil.which("node")
    if not node or not (ROOT/"web/node_modules/jsdom/package.json").is_file():
        pytest.skip("requires Node.js and web npm ci")
    result=subprocess.run([node,str(ROOT/"tests/web_readiness_runtime.cjs"),case],cwd=ROOT,
        capture_output=True,text=True,encoding="utf-8",timeout=25)
    assert result.returncode == 0,result.stdout+result.stderr
