"""Core agent runtime with high-fidelity streaming."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPartDelta,
    ThinkingPartDelta,
    ToolCallPartDelta,
)
from pydantic_ai.models import Model
from pydantic_ai.tools import Tool

T = TypeVar("T")
DepsT = TypeVar("DepsT")


@dataclass
class StreamHandlers:
    """Callbacks mapping to every stage of the LLM lifecycle.

    This allows the UI to perfectly reconstruct the Agent's thought process.

    Lifecycle Events:
        on_block_start: A new block (Text, Thinking, or Tool Call) has started.
        on_block_end: A block has finished generating.
        on_complete: The entire response is finished.

    Content Events (Typing Effect):
        on_text_delta: Incremental text content.
        on_thinking_delta: Incremental thinking/reasoning content.
        on_tool_call_delta: Incremental tool name and arguments as they form.

    Execution Events:
        on_tool_execute: Tool call is fully formed and NOW executing.
        on_tool_result: Tool has finished and returned data.

    Example:
        handlers = StreamHandlers(
            on_block_start=lambda kind, idx: print(f"[Start {kind} #{idx}]"),
            on_text_delta=lambda txt: print(txt, end=""),
            on_tool_execute=lambda id, name, args: print(f"[Running {name}...]"),
            on_tool_result=lambda id, name, res: print(f"[Result: {res}]"),
            on_complete=lambda data: print(f"[Done: {data}]"),
        )
    """

    # Lifecycle: Block open/close
    on_block_start: Callable[[str, int], None] | None = None  # (type, index)
    on_block_end: Callable[[str, int], None] | None = None  # (type, index)

    # Content: Incremental deltas
    on_text_delta: Callable[[str], None] | None = None
    on_thinking_delta: Callable[[str], None] | None = None
    on_tool_call_delta: Callable[[str, str], None] | None = None  # (name_delta, args_delta)

    # Execution: Tool running/results
    on_tool_execute: Callable[[str, str, dict[str, Any]], None] | None = None  # (id, name, args)
    on_tool_result: Callable[[str, str, str], None] | None = None  # (id, name, result_str)

    # Lifecycle: Response complete
    on_complete: Callable[[Any], None] | None = None


@dataclass
class BondAgent(Generic[T, DepsT]):
    """Generic agent runtime wrapping PydanticAI with full-spectrum streaming.

    A BondAgent provides:
    - High-fidelity streaming with callbacks for every lifecycle event
    - Block start/end notifications for UI rendering
    - Real-time streaming of text, thinking, and tool arguments
    - Tool execution and result callbacks
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
            on_text_delta=lambda t: print(t, end=""),
            on_tool_execute=lambda id, name, args: print(f"[Running {name}]"),
        )

        response = await agent.ask("Remember my preference", handlers=handlers)
    """

    name: str
    instructions: str
    model: str | Model
    toolsets: Sequence[Sequence[Tool[DepsT]]] = field(default_factory=list)
    deps: DepsT | None = None
    output_type: type[T] = str  # type: ignore[assignment]
    max_retries: int = 3

    _agent: Agent[DepsT, T] | None = field(default=None, init=False, repr=False)
    _history: list[ModelMessage] = field(default_factory=list, init=False, repr=False)
    _tool_names: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _tools: list[Tool[DepsT]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the underlying PydanticAI agent."""
        all_tools: list[Tool[DepsT]] = []
        for toolset in self.toolsets:
            all_tools.extend(toolset)

        # Store tools for reuse when creating dynamic agents
        self._tools = all_tools

        # Only pass system_prompt if instructions are non-empty
        # This matches behavior when using raw Agent without system_prompt
        agent_kwargs: dict[str, Any] = {
            "model": self.model,
            "tools": all_tools,
            "output_type": self.output_type,
            "retries": self.max_retries,
            "deps_type": type(self.deps) if self.deps else None,
        }
        if self.instructions:
            agent_kwargs["system_prompt"] = self.instructions

        self._agent = Agent(**agent_kwargs)

    async def ask(
        self,
        prompt: str,
        *,
        handlers: StreamHandlers | None = None,
        dynamic_instructions: str | None = None,
    ) -> T:
        """Send prompt and get response with high-fidelity streaming.

        Args:
            prompt: The user's message/question.
            handlers: Optional callbacks for streaming events.
            dynamic_instructions: Override system prompt for this call only.

        Returns:
            The agent's response of type T.
        """
        if self._agent is None:
            raise RuntimeError("Agent not initialized")

        active_agent = self._agent
        if dynamic_instructions and dynamic_instructions != self.instructions:
            active_agent = Agent(
                model=self.model,
                system_prompt=dynamic_instructions,
                tools=self._tools,
                output_type=self.output_type,
                retries=self.max_retries,
                deps_type=type(self.deps) if self.deps else None,
            )

        if handlers:
            # Track tool call IDs to names for result lookup
            tool_id_to_name: dict[str, str] = {}

            async with active_agent.run_stream(
                prompt,
                deps=self.deps,
                message_history=self._history,
            ) as result:
                async for event in result.stream():
                    # --- 1. BLOCK LIFECYCLE (Open/Close) ---
                    if isinstance(event, PartStartEvent):
                        if handlers.on_block_start:
                            kind = getattr(event.part, "part_kind", "unknown")
                            handlers.on_block_start(kind, event.index)

                    elif isinstance(event, PartEndEvent):
                        if handlers.on_block_end:
                            kind = getattr(event.part, "part_kind", "unknown")
                            handlers.on_block_end(kind, event.index)

                    # --- 2. DELTAS (Typing Effect) ---
                    elif isinstance(event, PartDeltaEvent):
                        delta = event.delta

                        if isinstance(delta, TextPartDelta):
                            if handlers.on_text_delta:
                                handlers.on_text_delta(delta.content_delta)

                        elif isinstance(delta, ThinkingPartDelta):
                            if handlers.on_thinking_delta and delta.content_delta:
                                handlers.on_thinking_delta(delta.content_delta)

                        elif isinstance(delta, ToolCallPartDelta):
                            if handlers.on_tool_call_delta:
                                name_d = delta.tool_name_delta or ""
                                args_d = delta.args_delta or ""
                                # Handle dict args (rare but possible)
                                if isinstance(args_d, dict):
                                    args_d = json.dumps(args_d)
                                handlers.on_tool_call_delta(name_d, args_d)

                    # --- 3. EXECUTION (Tool Running/Results) ---
                    elif isinstance(event, FunctionToolCallEvent):
                        # Tool call fully formed, starting execution
                        tool_id_to_name[event.tool_call_id] = event.part.tool_name
                        if handlers.on_tool_execute:
                            handlers.on_tool_execute(
                                event.tool_call_id,
                                event.part.tool_name,
                                event.part.args_as_dict(),
                            )

                    elif isinstance(event, FunctionToolResultEvent):
                        # Tool returned data
                        if handlers.on_tool_result:
                            tool_name = tool_id_to_name.get(event.tool_call_id, "unknown")
                            handlers.on_tool_result(
                                event.tool_call_id,
                                tool_name,
                                str(event.result.content),
                            )

                    # --- 4. COMPLETION ---
                    elif isinstance(event, FinalResultEvent):
                        pass  # Handled after stream

                # Stream finished
                self._history = list(result.all_messages())

                if handlers.on_complete:
                    handlers.on_complete(result.output)

                data: T = result.output
                return data

        # Non-streaming fallback
        result = await active_agent.run(
            prompt,
            deps=self.deps,
            message_history=self._history,
        )
        self._history = list(result.all_messages())
        non_stream_data: T = result.output
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
