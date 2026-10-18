from uuid import uuid4

from netpilot.agent import SessionStore
from netpilot.agent.context_builder import build_task_context_message
from netpilot.agent.intent import TurnIntent
from netpilot.agent.prompts import NETPILOT_SYSTEM_PROMPT
from netpilot.environment import EnvironmentProfile, merge_environment
from reasoning_helpers import DiagnosticLLM, CASE_B, make_agent, run_session


def test_ep08_compact_context_separates_environment_from_evidence():
    profile = merge_environment(EnvironmentProfile(), {"vpn_enabled":False, "network_access":"campus_wifi"}, source="user")
    profile = merge_environment(profile, {"effective_type":"4g", "browser_online":True}, source="browser")
    text = build_task_context_message(user_message="网页打不开", intent=TurnIntent.DIAGNOSE, task_version=1, environment_profile=profile).content
    assert "ENVIRONMENT PROFILE" in text and "VPN: false (user confirmed)" in text
    assert "Proxy: unknown" in text and "Network access: campus_wifi (user confirmed)" in text
    assert "ABNORMAL EVIDENCE\n- none" in text
    assert "field_sources" not in text and '"browser_online"' not in text
    assert "unknown 不等于 false" in NETPILOT_SYSTEM_PROMPT
    assert "4g 不代表蜂窝网络" in NETPILOT_SYSTEM_PROMPT


def test_agent_updates_before_context_with_no_additional_llm_calls_and_keeps_profile():
    sessions, owner = SessionStore(), uuid4()
    sid = sessions.create(owner).session_id
    llm = DiagnosticLLM()
    agent = make_agent(llm)
    first = run_session(agent, sessions, sid, owner, "我现在用 Windows 11，连校园 WiFi，没开 VPN，微信正常但网页打不开。")
    profile = sessions.task_state(sid, owner).environment_profile
    assert profile.os_family == "windows" and profile.vpn_enabled is False and profile.proxy_enabled is None
    assert all("ENVIRONMENT PROFILE" in next(msg.content for msg in messages if "CURRENT TASK" in (msg.content or "")) for messages, _ in llm.calls)
    assert len(llm.calls) == 2  # Existing basic diagnostic round + answer, no extraction call.
    before = sessions.task_state(sid, owner)
    second = run_session(agent, sessions, sid, owner, CASE_B)
    assert second.environment_profile == profile
    assert sessions.task_state(sid, owner).task_version == before.task_version == 1
    assert first.environment_profile == profile


def test_knowledge_finalization_also_receives_profile_without_extra_calls():
    from test_knowledge_finalization import LLM, Retriever, completed
    from netpilot.agent import AgentOrchestrator, ToolRegistry
    from netpilot.config import Settings
    from netpilot.tools import build_network_tools
    llm = LLM([completed()])
    sessions, owner = SessionStore(), uuid4()
    sid = sessions.create(owner).session_id
    sessions.update_environment(sid, owner, {"os_family":"macos", "network_access":"off_campus", "vpn_enabled":None}, source="user")
    agent = AgentOrchestrator(llm, ToolRegistry(build_network_tools(Settings(_env_file=None)), Retriever()))
    run_session(agent, sessions, sid, owner, "天津大学 VPN 怎么使用？请检索知识库并标出来源。")
    assert len(llm.calls) == 2
    prompt = "\n".join(m.content or "" for m in llm.calls[-1][0])
    assert "ENVIRONMENT PROFILE" in prompt and "OS: macos (user confirmed)" in prompt
    assert "VPN: unknown" in prompt and "field_sources" not in prompt
