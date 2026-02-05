"""Assistant agent adapter for Temporal execution.

Wraps the existing DataingAssistant for use with the unified Temporal interface.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dataing.agents.assistant import DataingAssistant
from dataing.temporal.agents.base import BaseTemporalAgent
from dataing.temporal.agents.protocol import AgentTurnResult

logger = logging.getLogger(__name__)


class AssistantTemporalAgent(BaseTemporalAgent):
    """Wraps DataingAssistant for Temporal execution.

    This adapter allows the existing DataingAssistant to run through the
    unified Temporal agent workflow, providing:
    - Durable execution with automatic retries
    - Observability through Temporal UI
    - Consistent interface with other agents
    """

    AGENT_NAME = "dataing-assistant"

    def __init__(
        self,
        api_key: str,
        tenant_id: str,
        *,
        model: str = "claude-sonnet-4-20250514",
        repo_path: str | Path = ".",
        github_token: str | None = None,
        log_directories: list[str] | None = None,
    ) -> None:
        """Initialize the assistant agent.

        Args:
            api_key: Anthropic API key.
            tenant_id: Tenant ID for multi-tenancy isolation.
            model: LLM model to use.
            repo_path: Path to local git repository.
            github_token: Optional GitHub token for git tools.
            log_directories: Directories to scan for log files.
        """
        super().__init__(name=self.AGENT_NAME, tenant_id=tenant_id)

        # Create the underlying DataingAssistant
        self._assistant = DataingAssistant(
            api_key=api_key,
            tenant_id=tenant_id,
            model=model,
            repo_path=repo_path,
            github_token=github_token,
            log_directories=log_directories,
        )

        logger.info(f"AssistantTemporalAgent initialized for tenant {tenant_id}")

    async def _execute_turn(
        self,
        message: str,
        session_id: str,
        context: dict[str, Any],
    ) -> AgentTurnResult:
        """Execute one LLM turn using the DataingAssistant.

        Args:
            message: The user's message or prompt.
            session_id: Session ID for conversation continuity.
            context: Additional context (history, page context, etc.).

        Returns:
            AgentTurnResult with response and metadata.
        """
        logger.info(f"Processing message for session {session_id}: {message[:100]}...")

        # Call the underlying assistant
        # Note: DataingAssistant doesn't expose tool call details directly,
        # so we capture what we can from the response
        response = await self._assistant.ask(
            message,
            session_id=session_id,
            context=context,
        )

        logger.info(f"Assistant response length: {len(response)}")

        # Create the result
        # Since DataingAssistant handles tools internally, we rely on
        # the base class tool recording if we add instrumentation later
        return AgentTurnResult(
            response=response,
            tool_calls=self._get_tool_calls(),  # From base class if instrumented
            is_complete=False,  # Assistant conversations are ongoing until user ends
            tokens_used=0,  # DataingAssistant doesn't expose token counts yet
            metadata={
                "session_id": session_id,
                "tenant_id": self._tenant_id,
            },
        )


def create_assistant_agent(
    api_key: str,
    tenant_id: str,
    **kwargs: Any,
) -> AssistantTemporalAgent:
    """Factory function to create an AssistantTemporalAgent.

    Args:
        api_key: Anthropic API key.
        tenant_id: Tenant ID for multi-tenancy.
        **kwargs: Additional arguments passed to AssistantTemporalAgent.

    Returns:
        Configured AssistantTemporalAgent instance.
    """
    return AssistantTemporalAgent(
        api_key=api_key,
        tenant_id=tenant_id,
        **kwargs,
    )
