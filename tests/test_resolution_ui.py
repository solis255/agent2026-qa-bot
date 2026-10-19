from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case",["RS-BADGES","RS-CONFIRM","RS-ESCALATED","RS-RESOLVED","RS-HISTORY","RS-XSS","RS-RESET","RS-MOCK","RS-REMOTE-REVERIFY"])
def test_rs22_rs24_resolution_dom(case):
    node=shutil.which("node")
    if not node or not (ROOT/"web/node_modules/jsdom/package.json").is_file():pytest.skip("requires Node.js and web npm ci")
    result=subprocess.run([node,str(ROOT/"tests/web_resolution_runtime.cjs"),case],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
    assert result.returncode == 0,result.stdout+result.stderr
