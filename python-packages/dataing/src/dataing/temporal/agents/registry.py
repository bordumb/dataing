"""Registry for Temporal-compatible agents.

Provides a central registry for agents that can be executed through Temporal workflows.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dataing.temporal.agents.protocol import TemporalAgentProtocol

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry of agents available for Temporal execution.

    This is a simple registry pattern that allows agents to be registered
    and retrieved by name. The worker uses this to look up agents when
    executing the agent_turn activity.

    Usage:
        # Register an agent
        registry = AgentRegistry()
        registry.register(my_agent)

        # Get an agent
        agent = registry.get("dataing-assistant")
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._agents: dict[str, TemporalAgentProtocol] = {}

    def register(self, agent: TemporalAgentProtocol) -> None:
        """Register an agent.

        Args:
            agent: Agent implementing TemporalAgentProtocol.

        Raises:
            ValueError: If an agent with the same name is already registered.
        """
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' is already registered")
        self._agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name}")

    def get(self, name: str) -> TemporalAgentProtocol:
        """Get an agent by name.

        Args:
            name: The agent's unique identifier.

        Returns:
            The registered agent.

        Raises:
            KeyError: If no agent with the given name is registered.
        """
        if name not in self._agents:
            available = list(self._agents.keys())
            raise KeyError(f"Agent '{name}' not found. Available agents: {available}")
        return self._agents[name]

    def list_agents(self) -> list[str]:
        """List all registered agent names.

        Returns:
            List of agent names.
        """
        return list(self._agents.keys())

    def has(self, name: str) -> bool:
        """Check if an agent is registered.

        Args:
            name: The agent's unique identifier.

        Returns:
            True if the agent is registered.
        """
        return name in self._agents

    def clear(self) -> None:
        """Clear all registered agents (useful for testing)."""
        self._agents.clear()
