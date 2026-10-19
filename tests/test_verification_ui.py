from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case",["BV-REMOTE","BV-HOST","BV-TABLE","BV-RESULTS","BV-OBSERVATION","BV-HISTORY","BV-XSS","BV-RESET"])
def test_bv20_verification_dom(case):
    node=shutil.which("node")
    if not node or not (ROOT/"web/node_modules/jsdom/package.json").is_file():pytest.skip("requires Node.js and web npm ci")
    result=subprocess.run([node,str(ROOT/"tests/web_verification_runtime.cjs"),case],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
    assert result.returncode == 0,result.stdout+result.stderr
