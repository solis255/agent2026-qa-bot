from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", ["DT-REMOTE","DT-SWITCH","DT-MOCK","DT-TIMELINE","DT-REFRESH","DT-HISTORY","DT-RESET"])
def test_target_dom(case):
    node = shutil.which("node")
    if not node or not (ROOT / "web/node_modules/jsdom/package.json").is_file():
        pytest.skip("Target UI tests require Node.js and `cd web && npm ci`")
    result = subprocess.run([node,str(ROOT / "tests/web_target_runtime.cjs"),case],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
    assert result.returncode == 0, result.stdout + result.stderr
