from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case",["GR-EMPTY","GR-ORDER","GR-FEEDBACK","GR-CITATION","GR-HISTORY","GR-RESET","GR-SUPERSEDED","GR-XSS"])
def test_gr20_remediation_dom(case):
    node=shutil.which("node")
    if not node or not (ROOT/"web/node_modules/jsdom/package.json").is_file():
        pytest.skip("requires Node.js and web npm ci")
    result=subprocess.run([node,str(ROOT/"tests/web_remediation_runtime.cjs"),case],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
    assert result.returncode == 0,result.stdout+result.stderr
