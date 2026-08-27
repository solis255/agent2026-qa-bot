from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_web_demo_contains_all_milestone_six_surfaces() -> None:
    html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")

    for element_id in (
        "conversation",
        "chat-form",
        "new-session",
        "scenario-select",
        "diagnosis-summary",
        "tool-timeline",
        "source-list",
    ):
        assert f'id="{element_id}"' in html
    assert "DNS 故障" in html
    assert "VPN 使用" in html


def test_web_javascript_uses_same_origin_api_and_safe_dom_rendering() -> None:
    javascript = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for endpoint in ("/api/health", "/api/session", "/api/chat", "/api/scenarios"):
        assert endpoint in javascript
    assert "textContent" in javascript
    assert "innerHTML" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert 'rel = "noopener noreferrer"' in javascript
    assert "diagnosis.summary" in javascript


def test_web_styles_include_mobile_and_accessible_states() -> None:
    stylesheet = (PROJECT_ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert "@media (max-width: 920px)" in stylesheet
    assert "@media (max-width: 560px)" in stylesheet
    assert ":focus-visible" in stylesheet
    assert ".timeline-item.abnormal" in stylesheet
    assert ".source-type.community" in stylesheet
