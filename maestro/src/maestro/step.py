"""Step protocol for workflow steps.

Steps are the building blocks of workflows. They are pure functions that
transform context and produce signals for workflow control flow.
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar, runtime_checkable

from maestro.result import StepResult

ContextT = TypeVar("ContextT", contravariant=True)
InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@runtime_checkable
class Step(Protocol[ContextT, InputT, OutputT]):
    """Protocol for workflow steps.

    Steps are:
    - Stateless: All state comes from context
    - Pure: Same input -> same output (modulo external services)
    - Composable: Can be chained, branched, merged

    This is a Protocol (structural subtyping), not an ABC.
    Any class with the right methods satisfies this protocol.

    Type Parameters:
        ContextT: The workflow context type (contravariant).
        InputT: The step input type (contravariant).
        OutputT: The step output type (covariant).

    Example:
        ```python
        @dataclass
        class MyContext:
            value: int

        class DoubleStep:
            @property
            def name(self) -> str:
                return "double"

            async def execute(
                self, context: MyContext, input_data: None = None
            ) -> StepResult[MyContext, int]:
                new_ctx = MyContext(value=context.value * 2)
                return StepResult(
                    context=new_ctx,
                    signal=Signal.CONTINUE,
                    output=new_ctx.value
                )

            def can_execute(self, context: MyContext) -> bool:
                return context.value > 0

        # This satisfies Step[MyContext, None, int]
        step: Step[MyContext, None, int] = DoubleStep()
        assert isinstance(step, Step)  # True at runtime
        ```
    """

    @property
    def name(self) -> str:
        """Unique name identifying this step within a workflow.

        The name is used for:
        - Routing via StepResult.next_step
        - Logging and debugging
        - Step registry lookups
        """
        ...

    async def execute(
        self, context: ContextT, input_data: InputT | None = None
    ) -> StepResult[ContextT, OutputT]:
        """Execute the step logic.

        This is the core method that performs the step's work.
        Steps should be idempotent when possible.

        Args:
            context: Current workflow context. Steps should not mutate this
                directly; instead, create a new context in the result.
            input_data: Optional step-specific input. Many steps don't need
                input beyond the context.

        Returns:
            StepResult with:
            - Updated context (or same context if unchanged)
            - Signal indicating what the workflow should do next
            - Optional step output
            - Optional routing hints
        """
        ...

    def can_execute(self, context: ContextT) -> bool:
        """Check if prerequisites are met for this step.

        Override to add precondition checks. The workflow engine may
        use this to skip or fail steps that can't execute.

        Args:
            context: Current workflow context to check against.

        Returns:
            True if the step can execute, False otherwise.
        """
        ...
