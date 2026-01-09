"""Core agent runtime."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    PartStartEvent,
    TextPartDelta,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.models import Model
from pydantic_ai.tools import Tool

T = TypeVar("T")
DepsT = TypeVar("DepsT")


@dataclass
class ToolCallEvent:
    """Event emitted when agent calls a tool.

    Attributes:
        name: Tool name (may be partial during streaming if delta=True).
        args: Tool arguments (may be partial JSON string during streaming).
        delta: True if this is a partial streaming update, False if complete.
    """

    name: str
    args: dict[str, Any] | str
    delta: bool = False


@dataclass
class StreamHandlers:
    """Callbacks for streaming agent responses.

    Attributes:
        on_text: Called with each text chunk as it streams.
        on_tool_call: Called when agent invokes a tool (both deltas and complete).
        on_thinking: Called with thinking/reasoning content (extended thinking).
        on_node_start: Called when a new block starts (text, tool-call, thinking).
                       Useful for UI to know when to start a new "bubble".
        json_mode: If True, callbacks receive JSON-serializable dicts
                   instead of objects (useful for WebSocket/SSE).
    """

    on_text: Callable[[str], None] | None = None
    on_tool_call: Callable[[ToolCallEvent], None] | None = None
    on_thinking: Callable[[str], None] | None = None
    on_node_start: Callable[[str], None] | None = None
    json_mode: bool = False


@dataclass
class BondAgent(Generic[T, DepsT]):
    """Generic agent runtime wrapping PydanticAI.

    A BondAgent provides:
    - Streaming responses with callbacks for text, tool calls, and thinking
    - Real-time streaming of tool call arguments as they form
    - Block start notifications for UI rendering
    - Message history management
    - Dynamic instruction override
    - Toolset composition
    - Retry handling

    Example:
        agent = BondAgent(
            name="assistant",
            instructions="You are helpful.",
            model="anthropic:claude-sonnet-4-20250514",
            toolsets=[memory_toolset],
            deps=QdrantMemoryStore(),
        )

        handlers = StreamHandlers(
            on_text=lambda t: print(t, end=""),
            on_tool_call=lambda tc: print(f"[Tool: {tc.name}]" if not tc.delta else ""),
            on_thinking=lambda t: print(f"[Thinking: {t}]"),
            on_node_start=lambda kind: print(f"[New {kind} block]"),
        )

        response = await agent.ask("Remember my preference", handlers=handlers)
    """

    name: str
    instructions: str
    model: str | Model
    # Sequence for broader compatibility (lists, tuples, FunctionToolset)
    toolsets: Sequence[Sequence[Tool[DepsT]]] = field(default_factory=list)
    deps: DepsT | None = None
    output_type: type[T] = str  # type: ignore[assignment]
    max_retries: int = 3

    _agent: Agent[DepsT, T] | None = field(default=None, init=False, repr=False)
    _history: list[ModelMessage] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the underlying PydanticAI agent."""
        all_tools: list[Tool[DepsT]] = []
        for toolset in self.toolsets:
            all_tools.extend(toolset)

        self._agent = Agent(
            model=self.model,
            system_prompt=self.instructions,
            tools=all_tools,
            result_type=self.output_type,
            retries=self.max_retries,
            deps_type=type(self.deps) if self.deps else None,
        )

    async def ask(
        self,
        prompt: str,
        *,
        handlers: StreamHandlers | None = None,
        dynamic_instructions: str | None = None,
    ) -> T:
        """Send prompt and get response with optional streaming.

        Args:
            prompt: The user's message/question.
            handlers: Optional callbacks for streaming events.
            dynamic_instructions: Override system prompt for this call only.

        Returns:
            The agent's response of type T.
        """
        if self._agent is None:
            raise RuntimeError("Agent not initialized")

        # Handle dynamic instructions - clone agent if changed
        active_agent = self._agent
        if dynamic_instructions and dynamic_instructions != self.instructions:
            active_agent = Agent(
                model=self.model,
                system_prompt=dynamic_instructions,
                tools=list(self._agent._function_tools.values()),
                result_type=self.output_type,
                retries=self.max_retries,
                deps_type=type(self.deps) if self.deps else None,
            )

        if handlers:
            async with active_agent.run_stream(
                prompt,
                deps=self.deps,
                message_history=self._history,
            ) as result:
                async for node in result.stream():
                    # 1. Part Start Event (New Block)
                    # Useful for UI to know "start a new bubble"
                    if isinstance(node, PartStartEvent):
                        if handlers.on_node_start:
                            kind = "unknown"
                            if hasattr(node.part, "part_kind"):
                                kind = node.part.part_kind
                            handlers.on_node_start(kind)

                    # 2. Text Delta (Standard Typing)
                    elif isinstance(node, TextPartDelta):
                        if handlers.on_text:
                            handlers.on_text(node.content_delta)

                    # 3. Thinking Delta (Deep Reasoning)
                    elif isinstance(node, ThinkingPartDelta):
                        if handlers.on_thinking and node.content_delta:
                            handlers.on_thinking(node.content_delta)

                    # 4. Tool Call Delta (Streaming arguments being typed)
                    # See JSON arguments forming in real-time
                    elif isinstance(node, ToolCallPartDelta):
                        if handlers.on_tool_call:
                            name = node.tool_name_delta or ""
                            args = node.args_delta or ""
                            if name or args:
                                handlers.on_tool_call(
                                    ToolCallEvent(name=name, args=args, delta=True)
                                )

                    # 5. Tool Call Complete (Fully formed, about to execute)
                    elif isinstance(node, ToolCallPart):
                        if handlers.on_tool_call:
                            if handlers.json_mode:
                                args = (
                                    node.args
                                    if isinstance(node.args, str)
                                    else dict(node.args)
                                )
                                handlers.on_tool_call(
                                    ToolCallEvent(name=node.tool_name, args=args, delta=False)
                                )
                            else:
                                handlers.on_tool_call(
                                    ToolCallEvent(
                                        name=node.tool_name, args=node.args, delta=False
                                    )
                                )

                self._history = list(result.all_messages())
                data: T = result.data
                return data

        # Non-streaming execution
        result = await active_agent.run(
            prompt,
            deps=self.deps,
            message_history=self._history,
        )
        self._history = list(result.all_messages())
        non_stream_data: T = result.data
        return non_stream_data

    def get_message_history(self) -> list[ModelMessage]:
        """Get current conversation history."""
        return list(self._history)

    def set_message_history(self, history: list[ModelMessage]) -> None:
        """Replace conversation history."""
        self._history = list(history)

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history = []

    def clone_with_history(self, history: list[ModelMessage]) -> "BondAgent[T, DepsT]":
        """Create new agent instance with given history (for branching).

        This is useful for exploring multiple conversation paths
        or creating checkpoints.

        Args:
            history: The message history to use for the clone.

        Returns:
            A new BondAgent with the same configuration but different history.
        """
        clone: BondAgent[T, DepsT] = BondAgent(
            name=self.name,
            instructions=self.instructions,
            model=self.model,
            toolsets=list(self.toolsets),
            deps=self.deps,
            output_type=self.output_type,
            max_retries=self.max_retries,
        )
        clone.set_message_history(history)
        return clone
