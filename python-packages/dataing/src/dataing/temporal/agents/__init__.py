"""Unified Temporal interface for agents.

This package provides a DRY interface that allows any agent (Investigation, Assistant,
future agents) to run through Temporal with consistent observability.

Design Decision: LLM Turns as Activities
Each LLM request/response cycle is a Temporal activity. Tools execute within that
activity and are logged, but don't create separate activities. This balances
visibility with overhead.
"""

from dataing.temporal.agents.protocol import (
    AgentTurnInput,
    AgentTurnResult,
    AgentWorkflowInput,
    AgentWorkflowResult,
    TemporalAgentProtocol,
    ToolCall,
)
from dataing.temporal.agents.registry import AgentRegistry

__all__ = [
    "AgentRegistry",
    "AgentTurnInput",
    "AgentTurnResult",
    "AgentWorkflowInput",
    "AgentWorkflowResult",
    "TemporalAgentProtocol",
    "ToolCall",
]
