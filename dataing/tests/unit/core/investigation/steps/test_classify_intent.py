"""Tests for ClassifyIntentStep."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.classify_intent import (
    ClassifyIntentStep,
    RefinementIntent,
)
from maestro import Signal, StepType


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample context with synthesis."""
    return InvestigationContext(
        alert_summary="NULL rate spike in analytics.events",
        schema_info={"tables": ["events", "users"]},
        current_synthesis={
            "root_cause": "Mobile app v2.3 has a bug that fails to send user_id.",
            "confidence": 0.92,
            "recommendations": [
                "Roll back mobile app to v2.2",
                "Fix user_id serialization in mobile SDK",
            ],
        },
    )


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Create mock LLM client."""
    llm = AsyncMock()
    llm.classify_intent.return_value = RefinementIntent.CLARIFY
    return llm


class TestRefinementIntent:
    """Tests for RefinementIntent enum."""

    def test_intent_values(self) -> None:
        """All expected intent values exist."""
        assert RefinementIntent.MODIFY_QUERY == "modify_query"
        assert RefinementIntent.NEW_HYPOTHESIS == "new_hypothesis"
        assert RefinementIntent.CLARIFY == "clarify"
        assert RefinementIntent.REVISE_SYNTHESIS == "revise_synthesis"
        assert RefinementIntent.DRILL_DOWN == "drill_down"
        assert RefinementIntent.ACKNOWLEDGE == "acknowledge"


class TestClassifyIntentStep:
    """Tests for ClassifyIntentStep."""

    def test_step_type(self, mock_llm: AsyncMock) -> None:
        """Step has correct type."""
        step = ClassifyIntentStep(llm=mock_llm)
        assert step.step_type == StepType.CLASSIFY_INTENT

    def test_can_execute_always_true(
        self,
        mock_llm: AsyncMock,
        sample_context: InvestigationContext,
    ) -> None:
        """can_execute always returns True (intent classification always possible)."""
        step = ClassifyIntentStep(llm=mock_llm)
        assert step.can_execute(sample_context) is True

    @pytest.mark.asyncio
    async def test_execute_calls_llm_classify_intent(
        self,
        mock_llm: AsyncMock,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute calls LLM classify_intent with message and context."""
        step = ClassifyIntentStep(llm=mock_llm)
        user_message = "Can you investigate the upstream ETL job?"

        await step.execute(sample_context, {"user_message": user_message})

        mock_llm.classify_intent.assert_called_once_with(
            message=user_message,
            context=sample_context.current_synthesis,
        )

    @pytest.mark.asyncio
    async def test_execute_returns_intent_as_output(
        self,
        mock_llm: AsyncMock,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute returns the classified intent as output."""
        mock_llm.classify_intent.return_value = RefinementIntent.DRILL_DOWN
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "Tell me more"})

        assert result.output == RefinementIntent.DRILL_DOWN

    @pytest.mark.asyncio
    async def test_execute_stores_message_in_context(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute stores user message in chat_history."""
        # Use MODIFY_QUERY to avoid assistant response
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.MODIFY_QUERY
        step = ClassifyIntentStep(llm=mock_llm)
        user_message = "Can you investigate more?"

        result = await step.execute(sample_context, {"user_message": user_message})

        # Message should be added to chat_history
        assert len(result.context.chat_history) > 0
        assert result.context.chat_history[-1]["role"] == "user"
        assert result.context.chat_history[-1]["content"] == user_message


class TestClassifyIntentStepRouting:
    """Tests for ClassifyIntentStep intent-to-step routing."""

    @pytest.mark.asyncio
    async def test_modify_query_routes_to_generate_query(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """MODIFY_QUERY intent routes to GENERATE_QUERY step."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.MODIFY_QUERY
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "Try a different query"})

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.GENERATE_QUERY

    @pytest.mark.asyncio
    async def test_new_hypothesis_routes_to_generate_hypotheses(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """NEW_HYPOTHESIS intent routes to GENERATE_HYPOTHESES step."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.NEW_HYPOTHESIS
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(
            sample_context,
            {"user_message": "What about network issues?"},
        )

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_clarify_routes_to_await_user(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """CLARIFY intent routes to AWAIT_USER step (will respond directly)."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.CLARIFY
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "What does that mean?"})

        assert result.signal == Signal.AWAIT_USER
        assert result.next_step == StepType.AWAIT_USER

    @pytest.mark.asyncio
    async def test_revise_synthesis_routes_to_synthesize(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """REVISE_SYNTHESIS intent routes to SYNTHESIZE step."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.REVISE_SYNTHESIS
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(
            sample_context,
            {"user_message": "Re-analyze with this new information"},
        )

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.SYNTHESIZE

    @pytest.mark.asyncio
    async def test_drill_down_routes_to_generate_hypotheses(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """DRILL_DOWN intent routes to GENERATE_HYPOTHESES step."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.DRILL_DOWN
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "Tell me more about ETL"})

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_acknowledge_returns_complete(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """ACKNOWLEDGE intent returns COMPLETE signal."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.ACKNOWLEDGE
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "Thanks, that's helpful"})

        assert result.signal == Signal.COMPLETE
        assert result.output == RefinementIntent.ACKNOWLEDGE


class TestClassifyIntentStepErrorHandling:
    """Tests for ClassifyIntentStep error handling."""

    @pytest.mark.asyncio
    async def test_handles_empty_message(
        self,
        mock_llm: AsyncMock,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute handles empty message gracefully."""
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": ""})

        # Should still call LLM with empty message
        mock_llm.classify_intent.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_missing_message(
        self,
        mock_llm: AsyncMock,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute handles missing user_message in input_data."""
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {})

        # Should still call LLM with empty message
        mock_llm.classify_intent.assert_called_once()
        call_args = mock_llm.classify_intent.call_args
        assert call_args.kwargs["message"] == ""

    @pytest.mark.asyncio
    async def test_handles_none_input_data(
        self,
        mock_llm: AsyncMock,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute handles None input_data."""
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, None)

        # Should still call LLM with empty message
        mock_llm.classify_intent.assert_called_once()
        call_args = mock_llm.classify_intent.call_args
        assert call_args.kwargs["message"] == ""

    @pytest.mark.asyncio
    async def test_returns_fail_on_llm_error(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute returns FAIL signal when LLM raises error."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.side_effect = Exception("LLM API error")
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "test"})

        assert result.signal == Signal.FAIL

    @pytest.mark.asyncio
    async def test_preserves_context_fields_on_success(
        self,
        mock_llm: AsyncMock,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute preserves existing context fields."""
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "test"})

        assert result.context.alert_summary == sample_context.alert_summary
        assert result.context.schema_info == sample_context.schema_info
        assert result.context.current_synthesis == sample_context.current_synthesis


class TestClassifyIntentStepClarifyResponse:
    """Tests for ClassifyIntentStep clarification response handling."""

    @pytest.mark.asyncio
    async def test_clarify_generates_response(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """CLARIFY intent generates a clarification response."""
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.CLARIFY
        mock_llm.generate_clarification.return_value = (
            "The mobile app bug causes the user_id field to be null..."
        )
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "What does that mean?"})

        # Should generate clarification
        mock_llm.generate_clarification.assert_called_once()

    @pytest.mark.asyncio
    async def test_clarify_response_stored_in_chat_history(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """CLARIFY response is stored in chat_history."""
        clarification = "The mobile app bug causes the user_id field to be null..."
        mock_llm = AsyncMock()
        mock_llm.classify_intent.return_value = RefinementIntent.CLARIFY
        mock_llm.generate_clarification.return_value = clarification
        step = ClassifyIntentStep(llm=mock_llm)

        result = await step.execute(sample_context, {"user_message": "What does that mean?"})

        # Response should be in chat_history
        assistant_messages = [
            m for m in result.context.chat_history if m["role"] == "assistant"
        ]
        assert len(assistant_messages) > 0
        assert assistant_messages[-1]["content"] == clarification
