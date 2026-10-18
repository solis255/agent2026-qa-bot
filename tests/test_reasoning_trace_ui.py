from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", ["RT-13", "RT-14", "RT-HISTORY", "RT-SSE", "RT-RESET"])
def test_reasoning_trace_dom(case):
    node = shutil.which("node")
    if node is None or not (ROOT / "web/node_modules/jsdom/package.json").is_file():
        pytest.skip("Trace UI tests require Node.js and `cd web && npm ci`")
    result = subprocess.run([node, str(ROOT / "tests/web_reasoning_runtime.cjs"), case], cwd=ROOT,
                            capture_output=True, text=True, timeout=25, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
