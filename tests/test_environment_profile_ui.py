from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", ["EP-BROWSER", "EP-UNSUPPORTED", "EP-EDIT", "EP-REFRESH", "EP-ISOLATION", "EP-HISTORY", "EP-RESET", "EP-PRIVACY"])
def test_environment_profile_dom(case):
    node = shutil.which("node")
    if node is None or not (ROOT / "web/node_modules/jsdom/package.json").is_file():
        pytest.skip("Environment UI tests require Node.js and `cd web && npm ci`")
    result = subprocess.run([node, str(ROOT / "tests/web_environment_runtime.cjs"), case], cwd=ROOT,
                            capture_output=True, text=True, timeout=25, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
