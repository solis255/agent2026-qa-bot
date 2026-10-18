import json
from uuid import uuid4

from netpilot.api.presenters import present_chat
from netpilot.history import SQLiteDiagnosisRepository
from netpilot.reports import build_diagnosis_report, export_diagnosis_report
from reasoning_helpers import CASE_A, make_agent


def test_rt12_report_and_exports_contain_safe_reasoning_trace(tmp_path):
    result = make_agent().run(CASE_A)
    record = SQLiteDiagnosisRepository(tmp_path / "report.db").upsert_session(uuid4(), CASE_A, present_chat(uuid4(), result))
    report = build_diagnosis_report(record)
    assert report.reasoning_trace == record.reasoning_trace
    markdown = export_diagnosis_report(report, "markdown").content.decode()
    payload = json.loads(export_diagnosis_report(report, "json").content)
    assert "## 诊断思路" in markdown
    assert "**识别任务**" in markdown
    assert "## 会话记录" in markdown and "## 参考知识" in markdown
    assert len(payload["reasoning_trace"]) == len(result.reasoning_trace)
    for forbidden in ("chain_of_thought", "hidden_reasoning", "raw_reasoning", "完整 System Prompt"):
        assert forbidden not in payload
        assert forbidden not in markdown
    assert result.reasoning_summary_llm_used is False


def test_report_trace_markdown_escapes_html_and_does_not_execute_model_text(tmp_path):
    result = make_agent().run(CASE_A)
    result.reasoning_trace[0] = result.reasoning_trace[0].model_copy(update={"title":"<img onerror=alert(1)>", "summary":"<script>alert(1)</script>"})
    record = SQLiteDiagnosisRepository(tmp_path / "escaped.db").upsert_session(uuid4(), CASE_A, present_chat(uuid4(), result))
    markdown = export_diagnosis_report(build_diagnosis_report(record), "markdown").content.decode()
    assert "<script>" not in markdown and "<img" not in markdown
    assert "&lt;script&gt;" in markdown
