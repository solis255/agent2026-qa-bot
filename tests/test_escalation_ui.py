from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case",["EP24-CARD","EP24-GENERATE","EP24-HISTORY","EP24-PREVIEW","EP24-XSS","EP24-RESET","EP24-STALE","EP24-SESSION-GUARD","EP24-ASYNC-GUARD"])
def test_ep24_browser_dom(case):
    node=shutil.which("node")
    if not node or not (ROOT/"web/node_modules/jsdom/package.json").is_file():pytest.skip("requires Node.js and web npm ci")
    result=subprocess.run([node,str(ROOT/"tests/web_escalation_runtime.cjs"),case],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
    assert result.returncode==0,result.stdout+result.stderr
