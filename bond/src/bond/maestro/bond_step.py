"""BondStep base class for AI-powered workflow steps.

BondStep bridges BondAgent with maestro.Step, providing a standard
pattern for steps that use LLM agents.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from bond.agent import BondAgent, StreamHandlers
from maestro import Signal, StepResult

ContextT = TypeVar("ContextT")
InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
ResponseT = TypeVar("ResponseT")


class BondStep(ABC, Generic[ContextT, InputT, OutputT, ResponseT]):
    """Base class for steps that use BondAgent for AI operations.

    BondStep provides a template method pattern for AI-powered steps:
    1. create_agent() - Create the BondAgent for this step
    2. build_prompt() - Build the prompt from context and input
    3. map_response() - Map the agent's response to a StepResult

    The execute() method orchestrates these three methods to
    satisfy the maestro.Step protocol.

    Example:
        class GenerateHypothesesBondStep(
            BondStep[InvestigationContext, None, list[Hypothesis], str]
        ):
            step_type = StepType.GENERATE_HYPOTHESES

            def create_agent(self, context):
                return BondAgent(
                    name="hypothesis_generator",
                    instructions=HYPOTHESIS_PROMPT,
                    model="anthropic:claude-sonnet-4-20250514",
                )

            def build_prompt(self, context, input_data):
                return f"Generate hypotheses for: {context.alert_summary}"

            def map_response(self, response, context):
                hypotheses = parse_hypotheses(response)
                new_ctx = context.model_copy(update={"hypotheses": hypotheses})
                return StepResult(
                    context=new_ctx,
                    signal=Signal.BRANCH,
                    output=hypotheses,
                    branch_request=BranchRequest(...),
                )
    """

    # Subclasses must set step_type for maestro.Step protocol
    step_type: str

    def __init__(self, handlers: StreamHandlers | None = None) -> None:
        """Initialize the BondStep.

        Args:
            handlers: Optional stream handlers for real-time callbacks
                during agent execution.
        """
        self._handlers = handlers

    @property
    def name(self) -> str:
        """Return step name for maestro.Step protocol."""
        # Handle both enum and string step_type
        if hasattr(self.step_type, "value"):
            val: str = self.step_type.value
            return val
        return self.step_type

    @abstractmethod
    def create_agent(self, context: ContextT) -> BondAgent[ResponseT, Any]:
        """Create the BondAgent for this step.

        The agent is created fresh for each execution to allow
        context-specific configuration.

        Args:
            context: Current workflow context.

        Returns:
            Configured BondAgent instance.
        """
        ...

    @abstractmethod
    def build_prompt(self, context: ContextT, input_data: InputT | None) -> str:
        """Build the prompt to send to the agent.

        Args:
            context: Current workflow context.
            input_data: Optional step-specific input data.

        Returns:
            The prompt string to send to the agent.
        """
        ...

    @abstractmethod
    def map_response(
        self,
        response: ResponseT,
        context: ContextT,
    ) -> StepResult[ContextT, OutputT]:
        """Map the agent's response to a StepResult.

        This is where the response is parsed, the context is updated,
        and the signal/routing is determined.

        Args:
            response: The response from the BondAgent.
            context: Current workflow context.

        Returns:
            StepResult with updated context and signal.
        """
        ...

    def can_execute(self, context: ContextT) -> bool:
        """Check if prerequisites are met.

        Override in subclasses to add precondition checks.
        Default implementation always returns True.

        Args:
            context: Current workflow context.

        Returns:
            True if the step can execute, False otherwise.
        """
        return True

    async def execute(
        self,
        context: ContextT,
        input_data: InputT | None = None,
    ) -> StepResult[ContextT, OutputT]:
        """Execute the step using the BondAgent.

        This template method:
        1. Creates the agent via create_agent()
        2. Builds the prompt via build_prompt()
        3. Calls the agent's ask() method
        4. Maps the response via map_response()

        Args:
            context: Current workflow context.
            input_data: Optional step-specific input data.

        Returns:
            StepResult with updated context and signal.
        """
        agent = self.create_agent(context)
        prompt = self.build_prompt(context, input_data)

        try:
            response = await agent.ask(prompt, handlers=self._handlers)
            return self.map_response(response, context)
        except Exception:
            # Return FAIL signal on agent errors
            return StepResult(
                context=context,
                signal=Signal.FAIL,
                output=None,
            )
