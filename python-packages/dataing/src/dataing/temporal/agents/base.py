"""Base class for Temporal-compatible agents.

Provides common functionality for tool call logging and instrumentation.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from dataing.temporal.agents.protocol import AgentTurnResult, ToolCall

logger = logging.getLogger(__name__)


class BaseTemporalAgent(ABC):
    """Base class with tool call logging and common functionality.

    Subclasses should implement the `_execute_turn` method to perform the
    actual LLM interaction. This base class handles:
    - Tool call tracking and timing
    - Logging and instrumentation
    - Standard result formatting
    """

    def __init__(self, name: str, tenant_id: str | None = None) -> None:
        """Initialize the base agent.

        Args:
            name: Unique agent identifier.
            tenant_id: Optional tenant ID for multi-tenancy.
        """
        self._name = name
        self._tenant_id = tenant_id
        self._tool_calls: list[ToolCall] = []

    @property
    def name(self) -> str:
        """Unique agent identifier."""
        return self._name

    def _record_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        result: str,
        duration_ms: int,
    ) -> None:
        """Record a tool call for logging.

        Args:
            name: Tool name.
            arguments: Tool arguments.
            result: Tool result (may be truncated for logging).
            duration_ms: Execution time in milliseconds.
        """
        tool_call = ToolCall(
            name=name,
            arguments=arguments,
            result=result[:1000] if len(result) > 1000 else result,  # Truncate for logging
            duration_ms=duration_ms,
        )
        self._tool_calls.append(tool_call)
        logger.debug(f"Tool call recorded: {name} ({duration_ms}ms)")

    def _clear_tool_calls(self) -> None:
        """Clear recorded tool calls for a new turn."""
        self._tool_calls = []

    def _get_tool_calls(self) -> list[ToolCall]:
        """Get recorded tool calls for the current turn.

        Returns:
            List of tool calls recorded during the turn.
        """
        return self._tool_calls.copy()

    async def run_turn(
        self,
        message: str,
        session_id: str,
        context: dict[str, Any],
    ) -> AgentTurnResult:
        """Execute one LLM turn with instrumentation.

        Args:
            message: The user's message or prompt.
            session_id: Session ID for conversation continuity.
            context: Additional context (history, page context, etc.).

        Returns:
            AgentTurnResult with response, tool calls, and completion status.
        """
        # Clear previous turn's tool calls
        self._clear_tool_calls()

        start_time = time.monotonic()

        try:
            # Execute the turn (implemented by subclass)
            result = await self._execute_turn(message, session_id, context)

            # Add recorded tool calls if the subclass didn't provide any
            if not result.tool_calls:
                result = AgentTurnResult(
                    response=result.response,
                    tool_calls=self._get_tool_calls(),
                    is_complete=result.is_complete,
                    tokens_used=result.tokens_used,
                    metadata=result.metadata,
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.info(
                f"Agent turn completed: agent={self._name}, "
                f"tools={len(result.tool_calls)}, "
                f"tokens={result.tokens_used}, "
                f"duration_ms={duration_ms}"
            )

            return result

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                f"Agent turn failed: agent={self._name}, error={e}, duration_ms={duration_ms}"
            )
            raise

    @abstractmethod
    async def _execute_turn(
        self,
        message: str,
        session_id: str,
        context: dict[str, Any],
    ) -> AgentTurnResult:
        """Execute the actual LLM turn (implemented by subclass).

        Args:
            message: The user's message or prompt.
            session_id: Session ID for conversation continuity.
            context: Additional context (history, page context, etc.).

        Returns:
            AgentTurnResult with response, tool calls, and completion status.
        """
        ...
