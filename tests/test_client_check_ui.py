from pathlib import Path
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]
CASES=["CC-ACTION","CC-WIZARD","CC-UPLOAD-CONTINUE","CC-DROP","CC-KEYBOARD","CC-DUPLICATE","CC-STALE","CC-SKEW","CC-FILE-ERRORS","CC-SENSITIVE","CC-FORMAT","CC-DECLINE","CC-LIFECYCLE","CC-HISTORY-TARGET","CC-ASYNC-SWITCH","CC-RECHECK-UNSUPPORTED"]


@pytest.mark.parametrize("case",CASES)
def test_client_check_dom(case):
    node=shutil.which("node")
    if not node or not (ROOT/"web/node_modules/jsdom/package.json").is_file():pytest.skip("requires Node.js and web npm ci")
    result=subprocess.run([node,str(ROOT/"tests/web_client_check_runtime.cjs"),case],cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=25)
    assert result.returncode == 0,result.stdout+result.stderr
