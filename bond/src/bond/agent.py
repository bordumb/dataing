"""Core agent runtime."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.tools import Tool

T = TypeVar("T")
DepsT = TypeVar("DepsT")


@dataclass
class ToolCallEvent:
    """Event emitted when agent calls a tool."""

    name: str
    args: dict[str, Any]


@dataclass
class StreamHandlers:
    """Callbacks for streaming agent responses.

    Attributes:
        on_text: Called with each text chunk as it streams.
        on_tool_call: Called when agent invokes a tool.
        on_thinking: Called with thinking/reasoning content.
        json_mode: If True, callbacks receive JSON-serializable dicts
                   instead of objects (useful for WebSocket/SSE).
    """

    on_text: Callable[[str], None] | None = None
    on_tool_call: Callable[[ToolCallEvent], None] | None = None
    on_thinking: Callable[[str], None] | None = None
    json_mode: bool = False


@dataclass
class BondAgent(Generic[T, DepsT]):
    """Generic agent runtime wrapping PydanticAI.

    A BondAgent provides:
    - Streaming responses with callbacks
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

        response = await agent.ask("Remember my preference", handlers=handlers)
    """

    name: str
    instructions: str
    model: str | Model
    toolsets: list[list[Tool[DepsT]]] = field(default_factory=list)
    deps: DepsT | None = None
    output_type: type[T] = str  # type: ignore[assignment]
    max_retries: int = 3

    _agent: Agent[DepsT, T] | None = field(default=None, init=False, repr=False)
    _history: list[ModelMessage] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the underlying PydanticAI agent."""
        # Flatten toolsets into single list
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

        # Build effective system prompt
        effective_prompt = dynamic_instructions or self.instructions

        # Create a temporary agent if dynamic instructions differ
        agent = self._agent
        if dynamic_instructions and dynamic_instructions != self.instructions:
            agent = Agent(
                model=self.model,
                system_prompt=effective_prompt,
                tools=list(self._agent._function_tools.values()),
                result_type=self.output_type,
                retries=self.max_retries,
                deps_type=type(self.deps) if self.deps else None,
            )

        if handlers:
            # Use streaming
            async with agent.run_stream(
                prompt,
                deps=self.deps,
                message_history=self._history,
            ) as result:
                async for event in result.stream_text(delta=True):
                    if handlers.on_text:
                        handlers.on_text(event)

                # Update history after completion
                self._history = list(result.all_messages())

                data: T = result.data
                return data
        else:
            # Non-streaming
            result = await agent.run(
                prompt,
                deps=self.deps,
                message_history=self._history,
            )
            self._history = list(result.all_messages())
            data = result.data
            return data

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
        clone = BondAgent(
            name=self.name,
            instructions=self.instructions,
            model=self.model,
            toolsets=self.toolsets,
            deps=self.deps,
            output_type=self.output_type,
            max_retries=self.max_retries,
        )
        clone.set_message_history(history)
        return clone
