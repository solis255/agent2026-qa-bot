from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from netpilot.agent import AgentResult, AgentStatus, AgentToolStep
from netpilot.api.presenters import present_chat
from netpilot.config import Settings
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.llm import TokenUsage
from netpilot.main import create_app
from netpilot.models import DiagnosisReportView
from netpilot.rag import KnowledgeSource
from netpilot.reports import (
    DiagnosisReportTooLargeError,
    build_diagnosis_report,
    export_diagnosis_report,
    render_report_json,
    render_report_markdown,
)
from netpilot.tools.schemas import DNSLookupData, ToolResult


def _result(answer: str = "问题判断：DNS 解析异常。") -> AgentResult:
    return AgentResult(
        answer=answer,
        status=AgentStatus.COMPLETED,
        tool_rounds=1,
        steps=[
            AgentToolStep(
                round=1,
                tool_call_id="report_dns_call",
                tool_name="dns_lookup",
                arguments={"domain": "github.com"},
                result=ToolResult[DNSLookupData](
                    success=True,
                    tool="dns_lookup",
                    summary="域名解析失败",
                    data=DNSLookupData(resolved=False, addresses=[]),
                    duration_ms=7,
                ),
            )
        ],
        sources=[
            KnowledgeSource(
                title="校园网络资料",
                source="https://wiki.tjubot.cn/e-life/network",
                source_type="community",
                file="campus_network.md",
                chunk_id="report-source-1",
                score=0.91,
            )
        ],
        usage=TokenUsage(
            prompt_tokens=120,
            completion_tokens=30,
            total_tokens=150,
        ),
        llm_duration_ms=345.67,
    )


def _record(tmp_path: Path, question: str = "github.com 为什么打不开？"):
    repository = SQLiteDiagnosisRepository(tmp_path / "report.db")
    response = present_chat(uuid4(), _result())
    return repository.save(question, response)


def test_report_generation_is_deterministic_complete_and_markdown_safe(
    tmp_path: Path,
) -> None:
    question = "测试 <script>alert(1)</script> [链接](javascript:bad) | # 标题"
    record = _record(tmp_path, question)

    first = build_diagnosis_report(record)
    second = build_diagnosis_report(record)
    markdown = render_report_markdown(first)
    json_text = render_report_json(first)

    assert first == second
    assert first.report_id == record.record_id
    assert first.generated_at == record.created_at
    assert "# TJU NetPilot 故障诊断报告" in markdown
    for section in (
        "## 用户问题",
        "## 诊断结论",
        "## 执行指标",
        "## 检测证据",
        "## 建议操作",
        "## 结论限制",
        "## 参考知识",
    ):
        assert section in markdown
    assert "&lt;script&gt;" in markdown
    assert "<script>" not in markdown
    assert "未额外调用语言模型" in markdown
    assert "Total Token：150" in markdown
    assert "Tool 总耗时：7 ms" in markdown
    assert "https://wiki.tjubot.cn/e-life/network" in markdown

    parsed = DiagnosisReportView.model_validate(json.loads(json_text))
    assert parsed == first
    assert parsed.tool_calls[0].arguments == {"domain": "github.com"}


def test_report_artifacts_are_stable_bounded_and_safely_named(tmp_path: Path) -> None:
    report = build_diagnosis_report(_record(tmp_path))

    markdown = export_diagnosis_report(report, "markdown")
    repeated = export_diagnosis_report(report, "markdown")
    json_artifact = export_diagnosis_report(report, "json")

    assert markdown == repeated
    assert markdown.filename == f"netpilot-diagnosis-{report.record_id}.md"
    assert markdown.media_type == "text/markdown; charset=utf-8"
    assert json_artifact.filename.endswith(".json")
    assert json_artifact.media_type == "application/json; charset=utf-8"
    assert DiagnosisReportView.model_validate_json(json_artifact.content)

    try:
        export_diagnosis_report(report, "markdown", max_bytes=100)
    except DiagnosisReportTooLargeError:
        pass
    else:
        raise AssertionError("oversized report should be rejected")


class ReportAgent:
    def __init__(self, answer: str = "问题判断：DNS 解析异常。") -> None:
        self.answer = answer
        self.call_count = 0

    def run(self, message: str, *, history=()) -> AgentResult:
        del message, history
        self.call_count += 1
        return _result(self.answer)


def _report_app(
    database: Path,
    *,
    api_key: str = "report-test-secret",
    answer: str = "问题判断：DNS 解析异常。",
    max_bytes: int = 1_000_000,
):
    app = create_app(
        Settings(
            _env_file=None,
            tju_api_key=api_key,
            tool_mode="mock",
            rag_enabled=False,
            diagnosis_history_enabled=True,
            diagnosis_db_path=database,
            diagnosis_report_max_bytes=max_bytes,
        )
    )
    app.state.agent = ReportAgent(answer)
    return app


def _create_report_record(client: TestClient, question: str = "请诊断 DNS") -> str:
    session_id = client.post("/api/session").json()["session_id"]
    response = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": question},
    )
    assert response.status_code == 200
    return response.json()["record_id"]


def test_report_api_previews_and_exports_without_another_agent_call(
    tmp_path: Path,
) -> None:
    secret = "report-api-secret-that-must-not-leak"
    app = _report_app(tmp_path / "report.db", api_key=secret)
    agent = app.state.agent
    with TestClient(app) as client:
        record_id = _create_report_record(client)
        preview = client.get(f"/api/diagnoses/{record_id}/report")
        markdown = client.get(
            f"/api/diagnoses/{record_id}/export?format=markdown"
        )
        markdown_again = client.get(
            f"/api/diagnoses/{record_id}/export?format=markdown"
        )
        json_export = client.get(
            f"/api/diagnoses/{record_id}/export?format=json"
        )

    assert agent.call_count == 1
    assert preview.status_code == 200
    assert preview.json()["report_id"] == record_id
    assert markdown.status_code == 200
    assert markdown.content == markdown_again.content
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert markdown.headers["content-disposition"] == (
        f'attachment; filename="netpilot-diagnosis-{record_id}.md"'
    )
    assert markdown.headers["cache-control"] == "private, no-store"
    assert markdown.headers["x-content-type-options"] == "nosniff"
    assert json_export.headers["content-type"].startswith("application/json")
    exported = DiagnosisReportView.model_validate_json(json_export.content)
    assert str(exported.record_id) == record_id
    combined = preview.content + markdown.content + json_export.content
    assert secret.encode() not in combined


def test_report_api_rejects_missing_invalid_oversized_and_disabled_exports(
    tmp_path: Path,
) -> None:
    app = _report_app(
        tmp_path / "report.db",
        answer="诊断结果" + "x" * 5000,
        max_bytes=1024,
    )
    with TestClient(app) as client:
        record_id = _create_report_record(client)
        oversized = client.get(
            f"/api/diagnoses/{record_id}/export?format=markdown"
        )
        invalid = client.get(f"/api/diagnoses/{record_id}/export?format=pdf")
        missing_format = client.get(f"/api/diagnoses/{record_id}/export")
        missing_report = client.get(f"/api/diagnoses/{uuid4()}/report")
        missing_export = client.get(
            f"/api/diagnoses/{uuid4()}/export?format=json"
        )

    disabled = create_app(
        Settings(
            _env_file=None,
            diagnosis_history_enabled=False,
            rag_enabled=False,
        )
    )
    with TestClient(disabled) as client:
        unavailable = client.get(
            f"/api/diagnoses/{UUID(int=0)}/export?format=json"
        )

    assert oversized.status_code == 413
    assert invalid.status_code == 422
    assert missing_format.status_code == 422
    assert missing_report.status_code == 404
    assert missing_export.status_code == 404
    assert unavailable.status_code == 503
    assert str(tmp_path) not in oversized.text
