import json
import pytest
from escalation_helpers import case
from netpilot.escalation.builder import build_package
from netpilot.escalation.exports import export_package
from netpilot.escalation.models import EscalationPackage
from netpilot.reports import DiagnosisReportTooLargeError


def test_ep20_ep21_self_contained_sections_and_json_schema():
    p=build_package(case())
    text=export_package(p,"md").content.decode()
    assert text.count("\n## ")==13
    assert all(s in text for s in ["Before / After","客观","主观","隐私处理","完整度","未提交工单"])
    assert EscalationPackage.model_validate(json.loads(export_package(p,"json").content))==p
    with pytest.raises(DiagnosisReportTooLargeError):export_package(p,"md",max_bytes=10)


def test_ep22_ep23_no_raw_data_transcript_prompt_or_hidden_reasoning():
    task=case()
    task.evidence[-1].data.update(raw_snapshot="RAW-SENTINEL",chain_of_thought="COT-SENTINEL",system_prompt="PROMPT-SENTINEL",conversation_turns="CHAT-SENTINEL")
    for format in ["md","json"]:
        text=export_package(build_package(task),format).content.decode()
        assert not any(s in text for s in ["RAW-SENTINEL","COT-SENTINEL","PROMPT-SENTINEL","CHAT-SENTINEL"])


def test_export_rejects_tampered_digest_and_markdown_escapes():
    task=case();task.remediation_symptom="<script>evil()</script> | X"
    p=build_package(task);text=export_package(p,"md").content.decode()
    assert "<script>" not in text and "\\| X" in text
    with pytest.raises(ValueError):export_package(p.model_copy(update={"package_version":99}),"json")
