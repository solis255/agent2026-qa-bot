"""Bounded native Function Calling loop for NetPilot diagnoses."""

from __future__ import annotations

from netpilot.agent.prompts import NETPILOT_SYSTEM_PROMPT
from netpilot.agent.schemas import AgentResult, AgentStatus, AgentToolStep
from netpilot.agent.tool_registry import ToolRegistry
from netpilot.llm import (
    ChatMessage,
    ChatRole,
    LLMClient,
    TJUClientError,
    TokenUsage,
)
from netpilot.rag import KnowledgeSearchData, KnowledgeSource


MAX_TOOL_ROUNDS_ANSWER = "已达到自动诊断步骤上限，当前证据不足以继续自动分析。"


class AgentOrchestrator:
    """Coordinate the model and allowlisted tools without arbitrary execution."""

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        *,
        max_tool_rounds: int = 6,
        system_prompt: str = NETPILOT_SYSTEM_PROMPT,
    ) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds must be at least 1")
        self.llm = llm
        self.registry = registry
        self.max_tool_rounds = max_tool_rounds
        self.system_prompt = system_prompt.strip()

    def run(self, user_message: str) -> AgentResult:
        """Run one isolated diagnosis until a final answer or safety stop."""

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=self.system_prompt),
            ChatMessage(role=ChatRole.USER, content=user_message),
        ]
        steps: list[AgentToolStep] = []
        usage = TokenUsage()
        llm_duration_ms = 0.0
        tool_rounds = 0
        sources: list[KnowledgeSource] = []
        tools = self.registry.schemas()

        while True:
            try:
                response = self.llm.chat(
                    messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=1200,
                )
            except TJUClientError as exc:
                return AgentResult(
                    answer=str(exc),
                    status=AgentStatus.LLM_ERROR,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                )

            usage = usage.add(response.usage)
            llm_duration_ms += response.duration_ms
            messages.append(response.to_assistant_message())

            if not response.tool_calls:
                assert response.content is not None
                return AgentResult(
                    answer=response.content,
                    status=AgentStatus.COMPLETED,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                )

            if tool_rounds >= self.max_tool_rounds:
                return AgentResult(
                    answer=MAX_TOOL_ROUNDS_ANSWER,
                    status=AgentStatus.MAX_TOOL_ROUNDS,
                    tool_rounds=tool_rounds,
                    steps=steps,
                    sources=sources,
                    usage=usage,
                    llm_duration_ms=llm_duration_ms,
                )

            tool_rounds += 1
            for tool_call in response.tool_calls:
                execution = self.registry.execute(
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                steps.append(
                    AgentToolStep(
                        round=tool_rounds,
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.function.name,
                        arguments=execution.arguments,
                        result=execution.result,
                    )
                )
                if tool_call.function.name == "knowledge_search":
                    sources = _merge_sources(sources, execution.result.data)
                messages.append(
                    ChatMessage(
                        role=ChatRole.TOOL,
                        tool_call_id=tool_call.id,
                        content=execution.result.model_dump_json(),
                    )
                )


def _merge_sources(
    existing: list[KnowledgeSource],
    data: object,
) -> list[KnowledgeSource]:
    if isinstance(data, KnowledgeSearchData):
        results = data.results
    elif isinstance(data, dict):
        try:
            results = KnowledgeSearchData.model_validate(data).results
        except ValueError:
            return existing
    else:
        return existing
    merged = list(existing)
    known = {source.chunk_id for source in merged}
    for result in results:
        if result.chunk_id in known:
            continue
        merged.append(
            KnowledgeSource(
                title=result.title,
                source=result.source,
                source_type=result.source_type,
                file=result.file,
                chunk_id=result.chunk_id,
                score=result.score,
            )
        )
        known.add(result.chunk_id)
    return merged
