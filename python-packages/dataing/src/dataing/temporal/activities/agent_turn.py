"""Generic agent turn activity for Temporal workflows.

This activity executes a single turn of any registered agent, providing
consistent observability and logging across all agent types.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from temporalio import activity

from dataing.temporal.agents.protocol import AgentTurnInput
from dataing.temporal.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentTurnActivityInput:
    """Input for the agent_turn activity (Temporal-serializable)."""

    agent_name: str
    message: str
    session_id: str
    context: dict[str, Any]
    tenant_id: str


def make_agent_turn_activity(registry: AgentRegistry) -> Any:
    """Create the agent_turn activity with injected registry.

    Args:
        registry: Agent registry containing registered agents.

    Returns:
        The agent_turn activity function.
    """

    @activity.defn(name="agent_turn")
    async def agent_turn(input: AgentTurnActivityInput) -> dict[str, Any]:
        """Execute a single turn of an agent.

        This activity:
        1. Looks up the agent in the registry
        2. Executes the turn with heartbeating
        3. Logs tool calls and metrics for observability
        4. Returns the serialized result

        Args:
            input: Agent turn input with message and context.

        Returns:
            Serialized AgentTurnResult as a dictionary.

        Raises:
            KeyError: If the agent is not registered.
            Exception: If the agent turn fails.
        """
        logger.info(f"Starting agent turn: agent={input.agent_name}, session={input.session_id}")

        # Get the agent from registry
        try:
            agent = registry.get(input.agent_name)
        except KeyError as e:
            logger.error(f"Agent not found: {input.agent_name}")
            raise e

        # Heartbeat to indicate we're starting
        activity.heartbeat(f"Starting turn for {input.agent_name}")

        start = time.monotonic()

        # Build context with tenant_id
        context = input.context.copy()
        context["tenant_id"] = input.tenant_id

        # Execute the agent turn
        result = await agent.run_turn(
            message=input.message,
            session_id=input.session_id,
            context=context,
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        # Heartbeat with progress
        activity.heartbeat(f"Turn completed for {input.agent_name}")

        # Log for Temporal visibility
        activity.logger.info(
            f"Agent turn completed: "
            f"agent={input.agent_name}, "
            f"session={input.session_id}, "
            f"tool_calls={len(result.tool_calls)}, "
            f"tokens={result.tokens_used}, "
            f"duration_ms={duration_ms}, "
            f"is_complete={result.is_complete}"
        )

        # Return serialized result
        result_dict: dict[str, Any] = result.to_dict()
        return result_dict

    return agent_turn


def from_input(input: AgentTurnInput) -> AgentTurnActivityInput:
    """Convert AgentTurnInput to AgentTurnActivityInput.

    Args:
        input: AgentTurnInput instance.

    Returns:
        AgentTurnActivityInput for the activity.
    """
    return AgentTurnActivityInput(
        agent_name=input.agent_name,
        message=input.message,
        session_id=input.session_id,
        context=input.context,
        tenant_id=input.tenant_id,
    )
