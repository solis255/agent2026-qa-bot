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
        "metrics-grid",
        "token-usage",
        "history-list",
        "history-refresh",
        "history-load-more",
        "report-actions",
        "report-preview",
        "export-markdown",
        "export-json",
        "report-dialog",
        "report-content",
    ):
        assert f'id="{element_id}"' in html
    assert "DNS 故障" in html
    assert "VPN 使用" in html


def test_web_javascript_uses_same_origin_api_and_safe_dom_rendering() -> None:
    javascript = (PROJECT_ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for endpoint in (
        "/api/health",
        "/api/session",
        "/api/chat",
        "/api/scenarios",
        "/api/diagnoses",
        "/report",
        "/export?format=",
    ):
        assert endpoint in javascript
    assert "textContent" in javascript
    assert "innerHTML" not in javascript
    assert "localStorage" not in javascript
    assert "sessionStorage" not in javascript
    assert 'rel = "noopener noreferrer"' in javascript
    assert "diagnosis.summary" in javascript
    assert "response.metrics" in javascript
    assert "record.user_message" in javascript
    assert "response.record_id" in javascript
    assert "response.body?.cancel()" in javascript
    assert "link.download" in javascript


def test_web_styles_include_mobile_and_accessible_states() -> None:
    stylesheet = (PROJECT_ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert "@media (max-width: 920px)" in stylesheet
    assert "@media (max-width: 560px)" in stylesheet
    assert ":focus-visible" in stylesheet
    assert ".timeline-item.abnormal" in stylesheet
    assert ".source-type.community" in stylesheet
    assert ".report-dialog::backdrop" in stylesheet
    assert ".report-actions" in stylesheet
