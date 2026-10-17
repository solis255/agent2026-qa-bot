"""Real DOM acceptance using the shipped Markdown parser and sanitizer, not mocks."""

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", ["MD-01", "MD-02", "MD-03", "MD-04", "MD-05", "MD-06", "MD-07", "SRC-04"])
def test_markdown_dom_runtime(case):
    node = shutil.which("node")
    if node is None or not (ROOT / "web/node_modules/jsdom/package.json").is_file():
        pytest.skip("Markdown DOM tests require Node.js and `cd web && npm ci`")
    result = subprocess.run(
        [node, str(ROOT / "tests/web_markdown_runtime.cjs"), case],
        cwd=ROOT, capture_output=True, text=True, timeout=25, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_vendored_assets_and_licenses_are_present():
    for name in ("marked.umd.js", "purify.min.js", "marked.LICENSE", "DOMPurify.LICENSE", "DOMPurify.LICENSE-MPL"):
        assert (ROOT / "web/vendor" / name).is_file()
    renderer = (ROOT / "web/markdown.js").read_text(encoding="utf-8")
    assert "DOMPurify.sanitize" in renderer
    assert "RETURN_DOM_FRAGMENT: true" in renderer
    assert "innerHTML" not in renderer
