"""ClassifyIntentStep implementation.

This step classifies user messages into refinement intents and routes
to the appropriate next step in the investigation workflow.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import StepType

from .protocol import Signal, Step, StepResult


class RefinementIntent(str, Enum):
    """Types of user refinement intents."""

    MODIFY_QUERY = "modify_query"
    NEW_HYPOTHESIS = "new_hypothesis"
    CLARIFY = "clarify"
    REVISE_SYNTHESIS = "revise_synthesis"
    DRILL_DOWN = "drill_down"
    ACKNOWLEDGE = "acknowledge"


class LLMProtocol(Protocol):
    """Protocol for LLM client used by ClassifyIntentStep."""

    async def classify_intent(
        self,
        *,
        message: str,
        context: dict[str, Any] | None,
    ) -> RefinementIntent:
        """Classify the user's message into a refinement intent.

        Args:
            message: The user's message to classify.
            context: Current synthesis context for understanding intent.

        Returns:
            The classified RefinementIntent.
        """
        ...

    async def generate_clarification(
        self,
        *,
        message: str,
        context: dict[str, Any] | None,
    ) -> str:
        """Generate a clarification response to the user's question.

        Args:
            message: The user's question.
            context: Current synthesis context.

        Returns:
            A clarification response string.
        """
        ...


# Mapping from intent to next step name
_INTENT_TO_NEXT_STEP: dict[RefinementIntent, str] = {
    RefinementIntent.MODIFY_QUERY: StepType.GENERATE_QUERY.value,
    RefinementIntent.NEW_HYPOTHESIS: StepType.GENERATE_HYPOTHESES.value,
    RefinementIntent.CLARIFY: StepType.AWAIT_USER.value,
    RefinementIntent.REVISE_SYNTHESIS: StepType.SYNTHESIZE.value,
    RefinementIntent.DRILL_DOWN: StepType.GENERATE_HYPOTHESES.value,
    RefinementIntent.ACKNOWLEDGE: StepType.COMPLETE.value,
}


class ClassifyIntentStep(Step[dict[str, Any] | None, RefinementIntent]):
    """Classify user message intent and route to appropriate step.

    This step:
    1. Extracts user message from input_data
    2. Calls LLM to classify intent
    3. Updates chat_history with user message
    4. For CLARIFY: generates response and adds to chat_history
    5. Routes to appropriate next step based on intent
    """

    step_type = StepType.CLASSIFY_INTENT

    def __init__(self, llm: LLMProtocol) -> None:
        """Initialize the step.

        Args:
            llm: LLM client for intent classification and clarification.
        """
        self.llm = llm

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if step can execute.

        Intent classification is always possible.

        Args:
            context: Current investigation context.

        Returns:
            Always True.
        """
        return True

    async def execute(
        self,
        context: InvestigationContext,
        input_data: dict[str, Any] | None = None,
    ) -> StepResult[InvestigationContext, RefinementIntent]:
        """Classify user message intent and route to next step.

        Args:
            context: Current investigation context.
            input_data: Dict with 'user_message' key, or None.

        Returns:
            StepResult with:
            - COMPLETE signal for ACKNOWLEDGE intent
            - AWAIT_USER signal for CLARIFY intent (with response)
            - CONTINUE signal for other intents with appropriate next_step
            - FAIL signal if LLM raises an error
        """
        # Extract user message
        user_message = ""
        if input_data is not None:
            user_message = input_data.get("user_message", "")

        try:
            # Classify intent
            intent: RefinementIntent = await self.llm.classify_intent(
                message=user_message,
                context=context.current_synthesis,
            )
        except Exception as e:
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                error=f"Intent classification failed: {e}",
            )

        # Add user message to chat_history
        new_chat_history = list(context.chat_history)
        new_chat_history.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # Handle CLARIFY intent - generate response
        if intent == RefinementIntent.CLARIFY:
            try:
                clarification = await self.llm.generate_clarification(
                    message=user_message,
                    context=context.current_synthesis,
                )
                new_chat_history.append(
                    {
                        "role": "assistant",
                        "content": clarification,
                    }
                )
            except Exception:
                # If clarification fails, just proceed without response
                pass

            updated_context = context.model_copy(update={"chat_history": new_chat_history})
            return StepResult(
                context=updated_context,
                signal=Signal.AWAIT_USER,
                output=intent,
                next_step=StepType.AWAIT_USER.value,
                await_token="clarify_user_input",
            )

        # Handle ACKNOWLEDGE intent - complete the branch
        if intent == RefinementIntent.ACKNOWLEDGE:
            updated_context = context.model_copy(update={"chat_history": new_chat_history})
            return StepResult(
                context=updated_context,
                signal=Signal.COMPLETE,
                output=intent,
            )

        # Handle other intents - continue to next step
        updated_context = context.model_copy(update={"chat_history": new_chat_history})
        next_step = _INTENT_TO_NEXT_STEP[intent]

        return StepResult(
            context=updated_context,
            signal=Signal.CONTINUE,
            output=intent,
            next_step=next_step,
        )
