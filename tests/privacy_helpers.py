from uuid import uuid4

from netpilot.agent import AgentResult, AgentStatus
from netpilot.api.presenters import present_chat


def response(answer="DNS 172.23.0.1 gateway 172.23.128.1 port 443", session_id=None):
    return present_chat(session_id or uuid4(), AgentResult(answer=answer, status=AgentStatus.COMPLETED, tool_rounds=0))
