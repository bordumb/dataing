"""The issue chat agent and one streamed turn of it.

This uses pydantic-ai's Agent directly rather than BondAgent: BondAgent takes no
model settings (needed for prompt caching and effort) and replays tool calls after
the text instead of streaming them.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Callable, Sequence
from typing import Any

from pydantic_ai import Agent, PromptedOutput, RunContext
from pydantic_ai.messages import (
    AgentStreamEvent,
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

from dataing.agents.chat.deps import ChatDeps, TurnResult, TurnUsage
from dataing.agents.chat.prompt import BRIEF_PROMPT, SYSTEM_PROMPT
from dataing.agents.chat.tools import CHAT_TOOLS
from dataing.core.investigation.brief import BriefDraft

TOOL_RETRIES = 2
MAX_OUTPUT_TOKENS = 16_000


def build_chat_model(model_name: str, api_key: str, effort: str | None) -> Model:
    """Return the Anthropic model for chat turns with prompt caching turned on.

    Args:
        model_name: Anthropic model id (settings.chat_agent_model).
        api_key: Anthropic API key.
        effort: "low", "medium" or "high"; empty or None leaves the model default.
    """
    settings = AnthropicModelSettings(
        max_tokens=MAX_OUTPUT_TOKENS,
        anthropic_cache_instructions=True,
        anthropic_cache_tool_definitions=True,
        anthropic_cache_messages=True,
    )
    if effort:
        settings["extra_body"] = {"output_config": {"effort": effort}}
    return AnthropicModel(
        model_name, provider=AnthropicProvider(api_key=api_key), settings=settings
    )


def build_chat_agent(model: Model | str) -> Agent[ChatDeps, str]:
    """Return a chat agent with the read-only tool set."""
    return Agent(
        model,
        deps_type=ChatDeps,
        output_type=str,
        instructions=SYSTEM_PROMPT,
        tools=CHAT_TOOLS,
        retries=TOOL_RETRIES,
    )


async def run_turn(
    agent: Agent[ChatDeps, str],
    deps: ChatDeps,
    prompt: str,
    history: Sequence[ModelMessage],
    on_text: Callable[[str], Any],
    *,
    instructions: str | None = None,
) -> TurnResult:
    """Run one agent turn, streaming text to on_text as it is generated.

    Args:
        agent: The chat agent.
        deps: Per-turn dependencies; tool calls and proposals are collected on it.
        prompt: The question being answered, labelled with its author.
        history: Earlier thread messages as model history.
        on_text: Called with each text delta, in order.
        instructions: Extra instructions for this run (the issue block).

    Returns:
        The streamed text, tool calls, steer proposals and token usage.
    """
    chunks: list[str] = []

    def emit(text: str) -> None:
        if text:
            chunks.append(text)
            on_text(text)

    async def handle_events(
        ctx: RunContext[ChatDeps], events: AsyncIterable[AgentStreamEvent]
    ) -> None:
        async for event in events:
            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                if chunks:
                    emit("\n\n")
                emit(event.part.content)
            elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                emit(event.delta.content_delta)

    result = await agent.run(
        prompt,
        deps=deps,
        message_history=list(history),
        instructions=instructions,
        event_stream_handler=handle_events,
    )
    run_usage = result.usage
    usage = TurnUsage(
        requests=run_usage.requests,
        input_tokens=run_usage.input_tokens,
        output_tokens=run_usage.output_tokens,
        cache_read_tokens=run_usage.cache_read_tokens,
        cache_write_tokens=run_usage.cache_write_tokens,
    )
    text = "".join(chunks).strip() or str(result.output)
    return TurnResult(
        text=text, tool_calls=list(deps.tool_calls), proposals=list(deps.proposals), usage=usage
    )


def build_brief_agent(model: Model | str) -> Agent[None, BriefDraft]:
    """Return the agent that drafts an investigation brief from a thread.

    The draft comes back as JSON text rather than through an output tool: an output
    tool makes pydantic-ai force tool_choice, which Claude Opus 5.5 rejects.
    """
    return Agent(
        model,
        output_type=PromptedOutput(BriefDraft),
        instructions=SYSTEM_PROMPT,
        retries=TOOL_RETRIES,
    )


async def draft_brief(
    agent: Agent[None, BriefDraft],
    history: Sequence[ModelMessage],
    *,
    instructions: str | None = None,
) -> tuple[BriefDraft, TurnUsage]:
    """Draft a brief from the thread history (no tools; structured output).

    Returns:
        The draft and the token usage of the call.
    """
    result = await agent.run(BRIEF_PROMPT, message_history=list(history), instructions=instructions)
    run_usage = result.usage
    usage = TurnUsage(
        requests=run_usage.requests,
        input_tokens=run_usage.input_tokens,
        output_tokens=run_usage.output_tokens,
        cache_read_tokens=run_usage.cache_read_tokens,
        cache_write_tokens=run_usage.cache_write_tokens,
    )
    return result.output, usage
