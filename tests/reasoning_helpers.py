"""Controlled LLM fixtures; decisions come from production Orchestrator/state."""

import json
import re

from netpilot.agent import AgentOrchestrator, ToolRegistry
from netpilot.config import Settings
from netpilot.llm import ChatResult, FunctionCall, LLMTimeoutError, ToolCall
from netpilot.main import create_app
from netpilot.tools import build_network_tools


CASE_A = "微信正常，但网页打不开，请完整排查。"
CASE_B = "基于刚才结果继续分析，不要重新检测。"
CASE_C = "把这次诊断整理成运维报告。"
CASE_D = "你刚才没有回答我的问题。"


class DiagnosticLLM:
    def __init__(self, *, finalization_error=False):
        self.calls = []
        self.round = 0
        self.finalization_error = finalization_error

    def chat(self, messages, **options):
        self.calls.append((list(messages), options))
        if options.get("tools") is None or options.get("tool_choice") == "none":
            if self.finalization_error:
                raise LLMTimeoutError("private-stack-payload-api-key-password", retryable=False)
            return ChatResult(content="依据已有结构化观察整理本轮回答，未验证的原因仍需核验。", model="test", duration_ms=1)
        if self.round % 2 == 0:
            calls = [("get_network_info", {}), ("dns_lookup", {"domain":"github.com"}),
                     ("dns_lookup", {"domain":"tju.edu.cn"}), ("ping_host", {"host":"8.8.8.8"})]
        else:
            calls = [("http_check", {"url":"https://example.test"})]
        self.round += 1
        return ChatResult(model="test", duration_ms=1, tool_calls=[
            # Deliberately reused transport IDs across Turns: Evidence IDs must not collide.
            ToolCall(id=f"call-{index}", function=FunctionCall(name=name, arguments=json.dumps(arguments)))
            for index, (name, arguments) in enumerate(calls)
        ])


def make_agent(llm=None, **options):
    return AgentOrchestrator(
        llm or DiagnosticLLM(),
        ToolRegistry(build_network_tools(Settings(_env_file=None, tool_mode="mock", mock_scenario="dns_failure"))),
        **options,
    )


def run_session(agent, sessions, sid, owner, message):
    history = sessions.begin_turn(sid, owner)
    result = agent.run(message, history=history, task_state=sessions.task_state(sid, owner))
    sessions.finish_turn(sid, message, result.answer, result=result)
    return result


def trace_app(tmp_path, **options):
    app = create_app(Settings(
        _env_file=None, tju_api_key="reasoning-test-key", tool_mode="mock", mock_scenario="dns_failure", rag_enabled=False,
        diagnosis_history_enabled=True, diagnosis_db_path=tmp_path / "trace.db", **options,
    ))
    app.state.agent = make_agent(
        reasoning_trace_enabled=app.state.settings.reasoning_trace_enabled,
        reasoning_trace_max_steps=app.state.settings.reasoning_trace_max_steps,
        reasoning_summary_llm_enabled=app.state.settings.reasoning_summary_llm_enabled,
    )
    return app
