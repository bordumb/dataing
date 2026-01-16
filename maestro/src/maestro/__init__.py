"""Maestro: Generic step-based workflow engine.

Maestro provides a simple, type-safe foundation for building
step-based workflows. It is intentionally minimal and generic,
with no dependencies on specific LLM libraries or domains.

Core concepts:
- Step: A unit of work that transforms context and produces signals
- StepResult: The result of executing a step
- Signal: Control flow instructions (CONTINUE, COMPLETE, FAIL, etc.)

Example:
    ```python
    from dataclasses import dataclass
    from maestro import Signal, Step, StepResult

    @dataclass(frozen=True)
    class MyContext:
        counter: int

    class IncrementStep:
        @property
        def name(self) -> str:
            return "increment"

        async def execute(
            self, context: MyContext, input_data: None = None
        ) -> StepResult[MyContext, None]:
            new_ctx = MyContext(counter=context.counter + 1)
            signal = Signal.COMPLETE if new_ctx.counter >= 10 else Signal.CONTINUE
            return StepResult(context=new_ctx, signal=signal)

        def can_execute(self, context: MyContext) -> bool:
            return True
    ```

"""

from maestro.handlers import (
    BranchContext,
    BranchingSignalHandler,
    DefaultSignalHandler,
    MergeStrategy,
    SignalHandler,
    SignalHandlerError,
    SignalResult,
)
from maestro.result import BranchRequest, BranchSpec, StepResult
from maestro.signals import Signal
from maestro.step import Step
from maestro.workflow import TickResult, Workflow, WorkflowError

__all__ = [
    "BranchContext",
    "BranchingSignalHandler",
    "BranchRequest",
    "BranchSpec",
    "DefaultSignalHandler",
    "MergeStrategy",
    "Signal",
    "SignalHandler",
    "SignalHandlerError",
    "SignalResult",
    "Step",
    "StepResult",
    "TickResult",
    "Workflow",
    "WorkflowError",
]

__version__ = "0.1.0"
