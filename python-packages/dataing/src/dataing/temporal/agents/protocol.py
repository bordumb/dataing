"""Protocol and types for Temporal-based agents.

Defines the interface that all Temporal-compatible agents must implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """Record of a tool invocation within an LLM turn."""

    name: str
    arguments: dict[str, Any]
    result: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCall:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            arguments=data.get("arguments", {}),
            result=data.get("result", ""),
            duration_ms=data.get("duration_ms", 0),
        )


@dataclass
class AgentTurnResult:
    """Result of a single LLM turn (may include tool calls)."""

    response: str
    tool_calls: list[ToolCall]
    is_complete: bool  # True if agent signals conversation complete
    tokens_used: int
    metadata: dict[str, Any] = field(default_factory=dict)  # Agent-specific data

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Temporal serialization."""
        return {
            "response": self.response,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "is_complete": self.is_complete,
            "tokens_used": self.tokens_used,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentTurnResult:
        """Create from dictionary."""
        return cls(
            response=data.get("response", ""),
            tool_calls=[ToolCall.from_dict(tc) for tc in data.get("tool_calls", [])],
            is_complete=data.get("is_complete", False),
            tokens_used=data.get("tokens_used", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentTurnInput:
    """Input to the agent_turn activity."""

    agent_name: str
    message: str
    session_id: str
    context: dict[str, Any] = field(default_factory=dict)  # History, page context, etc.
    tenant_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Temporal serialization."""
        return {
            "agent_name": self.agent_name,
            "message": self.message,
            "session_id": self.session_id,
            "context": self.context,
            "tenant_id": self.tenant_id,
        }


@dataclass
class AgentWorkflowInput:
    """Input for starting an agent workflow."""

    agent_name: str
    session_id: str
    tenant_id: str
    context: dict[str, Any] = field(default_factory=dict)
    initial_message: str | None = None  # Optional first message


@dataclass
class AgentWorkflowResult:
    """Result of a completed agent workflow."""

    session_id: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    status: str = "completed"


@runtime_checkable
class TemporalAgentProtocol(Protocol):
    """Interface for agents that run in Temporal.

    Any agent implementing this protocol can be registered with the AgentRegistry
    and executed through the generic AgentWorkflow.
    """

    @property
    def name(self) -> str:
        """Unique agent identifier (e.g., 'dataing-assistant', 'investigation-agent')."""
        ...

    async def run_turn(
        self,
        message: str,
        session_id: str,
        context: dict[str, Any],
    ) -> AgentTurnResult:
        """Execute one LLM turn (may include tool calls).

        Args:
            message: The user's message or prompt.
            session_id: Session ID for conversation continuity.
            context: Additional context (history, page context, etc.).

        Returns:
            AgentTurnResult with response, tool calls, and completion status.
        """
        ...
