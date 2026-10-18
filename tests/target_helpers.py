"""Controlled Local stand-in: counts handlers but never probes the real host."""
import json
from uuid import uuid4

from netpilot.agent import AgentOrchestrator, SessionStore, ToolRegistry
from netpilot.config import Settings
from netpilot.llm import ChatResult, FunctionCall, ToolCall
from netpilot.main import create_app
from netpilot.tools import build_network_tools
from test_knowledge_finalization import Retriever, citation

NETWORK_TOOLS = ("get_network_info", "ping_host", "dns_lookup", "tcp_check", "http_check", "traceroute")


class TargetLLM:
    def __init__(self):
        self.calls = []

    def chat(self, messages, **options):
        self.calls.append((list(messages), options))
        if any("KNOWLEDGE FINALIZATION" in (message.content or "") for message in messages):
            return ChatResult(content="按资料安装 VPN 客户端。" + citation(0),model="test",finish_reason="stop",duration_ms=1)
        names = [tool["function"]["name"] for tool in options.get("tools") or []]
        if "knowledge_search" in names:
            if any(message.role.value == "tool" for message in messages):
                return ChatResult(content="按资料安装 VPN 客户端。" + citation(0), model="test",duration_ms=1)
            return ChatResult(model="test",duration_ms=1, tool_calls=[ToolCall(id="rag",function=FunctionCall(name="knowledge_search",arguments='{"query":"天津大学VPN使用"}'))])
        if "dns_lookup" in names and options.get("tool_choice") != "none" and not any(message.role.value == "tool" for message in messages):
            return ChatResult(model="test",duration_ms=1, tool_calls=[ToolCall(id="dns",function=FunctionCall(name="dns_lookup",arguments='{"domain":"github.com"}'))])
        return ChatResult(content="你的设备 DNS 正常。", model="test",duration_ms=1)


def registry_and_counts(kind="local", *, rag=False):
    service = build_network_tools(Settings(_env_file=None, tool_mode="mock", mock_scenario="healthy"))
    service.provider.provider_name = kind
    counts = {name:0 for name in NETWORK_TOOLS}
    for name in NETWORK_TOOLS:
        handler = getattr(service, name)
        def counted(*args, _name=name, _handler=handler, **kwargs):
            counts[_name] += 1
            return _handler(*args, **kwargs)
        setattr(service, name, counted)
    return service, ToolRegistry(service, Retriever() if rag else None), counts


def local_session(*, rag=False, mode="remote_browser"):
    service, registry, counts = registry_and_counts("local", rag=rag)
    store = SessionStore(provider_kind="local", environment_client_mode=mode)
    owner = uuid4()
    sid = store.create(owner).session_id
    llm = TargetLLM()
    return AgentOrchestrator(llm, registry), store, sid, owner, counts, llm


def local_app(tmp_path, *, rag=False):
    app = create_app(Settings(_env_file=None,tju_api_key="target-test-key",tool_mode="local",rag_enabled=False,
                              diagnosis_history_enabled=True,diagnosis_db_path=tmp_path / "target.db"))
    service, registry, counts = registry_and_counts("local", rag=rag)
    app.state.network_tools = service
    app.state.tool_registry = registry
    app.state.agent = AgentOrchestrator(TargetLLM(), registry)
    return app, counts


def run(agent, store, sid, owner, message):
    history = store.begin_turn(sid, owner)
    result = agent.run(message,history=history,task_state=store.task_state(sid,owner))
    store.finish_turn(sid,message,result.answer,result=result)
    return result
