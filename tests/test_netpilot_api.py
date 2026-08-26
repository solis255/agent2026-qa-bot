from __future__ import annotations

from fastapi.testclient import TestClient

from netpilot.config import Settings
from netpilot.main import create_app


def build_client(api_key: str | None = None) -> TestClient:
    settings = Settings(
        _env_file=None,
        tju_api_key=api_key,
        tool_mode="mock",
        rag_enabled=True,
    )
    return TestClient(create_app(settings))


def test_health_reports_milestone_one_readiness() -> None:
    secret = "health-check-secret"

    with build_client(secret) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "llm_configured": True,
        "tool_mode": "mock",
        "rag_ready": False,
    }
    assert secret not in response.text
    assert "api_key" not in response.text.lower()


def test_application_starts_without_an_api_key() -> None:
    with build_client() as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["llm_configured"] is False


def test_application_factory_initializes_the_configured_tool_provider() -> None:
    settings = Settings(
        _env_file=None,
        tool_mode="mock",
        mock_scenario="tcp_ssh_blocked",
    )
    application = create_app(settings)

    assert application.state.network_tools.provider_name == "mock"
    assert application.state.network_tools.provider.scenario.value == "tcp_ssh_blocked"


def test_root_serves_the_chinese_web_shell() -> None:
    with build_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "TJU NetPilot" in response.text
    assert "校园网络智能诊断与服务 Agent" in response.text
    assert "工具执行步骤" in response.text
    assert "参考知识" in response.text


def test_web_assets_are_served_by_fastapi() -> None:
    with build_client() as client:
        javascript = client.get("/app.js")
        stylesheet = client.get("/style.css")
        favicon = client.get("/favicon.svg")

    assert javascript.status_code == 200
    assert 'fetch("/api/health"' in javascript.text
    assert stylesheet.status_code == 200
    assert ".workspace" in stylesheet.text
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
