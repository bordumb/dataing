"""Unit tests for BondStep."""

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from bond import BondAgent, BondStep, StreamHandlers
from maestro import Signal, Step, StepResult


@dataclass(frozen=True)
class SampleContext:
    """Sample context for testing."""

    value: str


class ConcreteBondStep(BondStep[SampleContext, str | None, str, str]):
    """Concrete implementation for testing."""

    step_type = "test_step"

    def __init__(
        self,
        agent_response: str = "mock response",
        handlers: StreamHandlers | None = None,
    ) -> None:
        """Initialize with configurable mock response."""
        super().__init__(handlers)
        self._agent_response = agent_response

    def create_agent(self, context: SampleContext) -> BondAgent[str, Any]:
        """Create a mock agent."""
        # Return a mock agent that will be used in tests
        mock_agent: Any = Mock(spec=BondAgent)
        mock_agent.ask = AsyncMock(return_value=self._agent_response)
        return mock_agent

    def build_prompt(self, context: SampleContext, input_data: str | None) -> str:
        """Build a simple prompt."""
        if input_data:
            return f"Context: {context.value}, Input: {input_data}"
        return f"Context: {context.value}"

    def map_response(
        self,
        response: str,
        context: SampleContext,
    ) -> StepResult[SampleContext, str]:
        """Map response to StepResult."""
        new_ctx = SampleContext(value=f"{context.value}-{response}")
        return StepResult(
            context=new_ctx,
            signal=Signal.CONTINUE,
            output=response,
            next_step="next",
        )


class FailingBondStep(BondStep[SampleContext, None, str, str]):
    """Step that fails during agent execution."""

    step_type = "failing_step"

    def create_agent(self, context: SampleContext) -> BondAgent[str, Any]:
        """Create an agent that raises an exception."""
        mock_agent: Any = Mock(spec=BondAgent)
        mock_agent.ask = AsyncMock(side_effect=Exception("Agent failed"))
        return mock_agent

    def build_prompt(self, context: SampleContext, input_data: None) -> str:
        """Build prompt."""
        return "test"

    def map_response(
        self,
        response: str,
        context: SampleContext,
    ) -> StepResult[SampleContext, str]:
        """Never reached due to exception."""
        return StepResult(context=context, signal=Signal.CONTINUE, output=response)


class TestBondStep:
    """Tests for BondStep base class."""

    def test_name_property_returns_step_type(self) -> None:
        """BondStep.name returns step_type value."""
        step = ConcreteBondStep()
        assert step.name == "test_step"

    def test_can_execute_returns_true_by_default(self) -> None:
        """Default can_execute returns True."""
        step = ConcreteBondStep()
        ctx = SampleContext(value="test")
        assert step.can_execute(ctx) is True

    @pytest.mark.asyncio
    async def test_execute_orchestrates_agent_call(self) -> None:
        """Execute calls create_agent, build_prompt, agent.ask, map_response."""
        step = ConcreteBondStep(agent_response="response123")
        ctx = SampleContext(value="initial")

        result = await step.execute(ctx, "input")

        assert result.signal == Signal.CONTINUE
        assert result.output == "response123"
        assert result.context.value == "initial-response123"
        assert result.next_step == "next"

    @pytest.mark.asyncio
    async def test_execute_without_input_data(self) -> None:
        """Execute works without input_data."""
        step = ConcreteBondStep(agent_response="no-input")
        ctx = SampleContext(value="test")

        result = await step.execute(ctx)

        assert result.output == "no-input"
        assert result.context.value == "test-no-input"

    @pytest.mark.asyncio
    async def test_execute_passes_handlers_to_agent(self) -> None:
        """Execute passes StreamHandlers to agent.ask."""
        handlers = StreamHandlers(on_text_delta=lambda t: None)
        step = ConcreteBondStep(handlers=handlers)
        ctx = SampleContext(value="test")

        # Override create_agent to capture the ask call
        mock_agent: Any = Mock(spec=BondAgent)
        mock_agent.ask = AsyncMock(return_value="response")
        step.create_agent = Mock(return_value=mock_agent)

        await step.execute(ctx)

        mock_agent.ask.assert_called_once()
        call_kwargs = mock_agent.ask.call_args[1]
        assert call_kwargs["handlers"] is handlers

    @pytest.mark.asyncio
    async def test_execute_returns_fail_on_agent_error(self) -> None:
        """Execute returns FAIL signal when agent raises exception."""
        step = FailingBondStep()
        ctx = SampleContext(value="test")

        result = await step.execute(ctx)

        assert result.signal == Signal.FAIL
        assert result.context == ctx  # Context unchanged
        assert result.output is None


class TestBondStepProtocol:
    """Tests for BondStep satisfying maestro.Step protocol."""

    def test_bond_step_satisfies_step_protocol(self) -> None:
        """BondStep instances satisfy Step protocol."""
        step = ConcreteBondStep()
        assert isinstance(step, Step)

    def test_step_has_required_methods(self) -> None:
        """BondStep has all methods required by Step protocol."""
        step = ConcreteBondStep()
        assert hasattr(step, "name")
        assert hasattr(step, "execute")
        assert hasattr(step, "can_execute")
        assert callable(step.execute)
        assert callable(step.can_execute)
