"""Tests for BondAgent.

These tests verify the agent runtime works correctly, especially
the dynamic_instructions override which creates a temporary agent.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from bond import BondAgent


class SimpleResponse(BaseModel):
    """Simple response model for testing."""

    message: str


class TestBondAgentDynamicInstructions:
    """Tests for BondAgent with dynamic_instructions.

    The key scenario: AgentClient uses empty instructions at init time,
    then passes the actual prompt via dynamic_instructions at call time.
    This is how the investigation agents work.
    """

    def test_agent_initialization_with_empty_instructions(self) -> None:
        """Test that BondAgent can be created with empty instructions.

        This is the pattern used by AgentClient - empty base instructions
        with dynamic_instructions provided at call time.
        """
        agent: BondAgent[str, None] = BondAgent(
            name="test-agent",
            instructions="",  # Empty, like AgentClient does
            model="test",
        )

        assert agent.name == "test-agent"
        assert agent.instructions == ""
        assert agent._agent is not None
        assert agent._tools == []  # No tools

    def test_agent_stores_tools_for_dynamic_agent_creation(self) -> None:
        """Test that tools are stored in _tools for reuse.

        When dynamic_instructions differ, a new Agent is created.
        It needs access to the same tools as the original.

        This test catches the bug where we tried to access
        self._agent._function_tools which doesn't exist.
        """
        agent: BondAgent[str, None] = BondAgent(
            name="test-agent",
            instructions="original",
            model="test",
            toolsets=[],  # No tools
        )

        # Tools should be stored in _tools (empty list in this case)
        assert agent._tools == []

        # This is the key assertion - _tools attribute exists and is accessible
        # The old code tried: self._agent._function_tools.values()
        # which would fail with AttributeError: 'Agent' object has no attribute '_function_tools'
        assert hasattr(agent, "_tools")

    @pytest.mark.asyncio
    async def test_dynamic_instructions_creates_new_agent(self) -> None:
        """Test that dynamic_instructions creates a temp agent with same tools.

        This is the core use case: AgentClient passes dynamic_instructions
        that differ from the base (empty) instructions, triggering creation
        of a new Agent with the dynamic system prompt.
        """
        with patch("bond.agent.Agent") as MockAgent:
            # Setup mock
            mock_agent_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.output = "test response"
            mock_result.all_messages.return_value = []
            mock_agent_instance.run = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_agent_instance

            agent: BondAgent[str, None] = BondAgent(
                name="test-agent",
                instructions="",  # Empty base
                model="test-model",
            )

            # Reset mock to track the dynamic agent creation
            MockAgent.reset_mock()

            # Call with dynamic_instructions
            await agent.ask(
                "test prompt",
                dynamic_instructions="You are a helpful assistant.",
            )

            # Verify a new Agent was created with the dynamic instructions
            MockAgent.assert_called_once()
            call_kwargs = MockAgent.call_args.kwargs

            assert call_kwargs["system_prompt"] == "You are a helpful assistant."
            assert call_kwargs["model"] == "test-model"
            assert call_kwargs["tools"] == []  # Our stored _tools (empty)

    @pytest.mark.asyncio
    async def test_same_instructions_reuses_existing_agent(self) -> None:
        """Test that same instructions reuses the existing agent."""
        with patch("bond.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.output = "test response"
            mock_result.all_messages.return_value = []
            mock_agent_instance.run = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_agent_instance

            agent: BondAgent[str, None] = BondAgent(
                name="test-agent",
                instructions="base instructions",
                model="test-model",
            )

            # First call creates the base agent
            initial_call_count = MockAgent.call_count

            # Call with same instructions as base
            await agent.ask(
                "test prompt",
                dynamic_instructions="base instructions",
            )

            # Should NOT create another agent
            assert MockAgent.call_count == initial_call_count


class TestBondAgentInitialization:
    """Tests for BondAgent initialization."""

    def test_agent_created_with_system_prompt_when_instructions_provided(self) -> None:
        """Test that system_prompt is set when instructions are non-empty."""
        with patch("bond.agent.Agent") as MockAgent:
            BondAgent(
                name="test",
                instructions="You are helpful.",
                model="test",
            )

            call_kwargs = MockAgent.call_args.kwargs
            assert call_kwargs["system_prompt"] == "You are helpful."

    def test_agent_created_without_system_prompt_when_instructions_empty(self) -> None:
        """Test that system_prompt is NOT set when instructions are empty."""
        with patch("bond.agent.Agent") as MockAgent:
            BondAgent(
                name="test",
                instructions="",
                model="test",
            )

            call_kwargs = MockAgent.call_args.kwargs
            assert "system_prompt" not in call_kwargs
