from pathlib import Path
import shutil
import subprocess
import pytest
from fastapi.testclient import TestClient
from target_helpers import local_app

ROOT=Path(__file__).resolve().parents[1]


def test_script_download_is_exact_readonly_asset(tmp_path):
    app,_=local_app(tmp_path)
    with TestClient(app) as client:
        response=client.get("/static/scripts/client_diagnostic_windows.ps1")
        assert response.status_code == 200
        assert response.content == (ROOT / "scripts/client_diagnostic_windows.ps1").read_bytes()
        assert "attachment" in response.headers["content-disposition"]
    script=response.text.casefold()
    for forbidden in ["set-net", "set-dns", "invoke-webrequest", "invoke-restmethod", "invoke-command", "start-process", "-executionpolicy", "set-executionpolicy", "new-pssession", "winrm", "set-itemproperty", "restart-service", "new-scheduledtask"]:
        assert forbidden not in script
    assert "get-netroute" in script and "'0.0.0.0/0'" in script


@pytest.mark.parametrize("case",["CS-EMPTY","CS-UPLOAD","CS-STALE","CS-ERROR","CS-DEDUP","CS-HISTORY","CS-RESET","CS-XSS"])
def test_cs18_snapshot_dom(case):
    node=shutil.which("node")
    if not node or not (ROOT / "web/node_modules/jsdom/package.json").is_file():
        pytest.skip("requires Node.js and web npm ci")
    result=subprocess.run([node,str(ROOT / "tests/web_client_snapshot_runtime.cjs"),case],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
    assert result.returncode == 0,result.stdout+result.stderr
