"""Maestro: Generic step-based workflow engine.

Maestro provides a simple, type-safe foundation for building
step-based workflows. It is intentionally minimal and generic,
with no dependencies on specific LLM libraries or domains.

Core concepts:
- Step: A unit of work that transforms context and produces signals
- StepResult: The result of executing a step
- Signal: Control flow instructions (CONTINUE, COMPLETE, FAIL, etc.)

New Event-Sourced Architecture (v2):
- Engine: Pure reducer for state transitions (state, event) -> (state, command)
- Runner: Async executor that runs commands and emits events
- Events: Immutable records of what happened during execution
- Replay: Deterministic state reconstruction from event logs

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

import warnings
from typing import Any

# New event-sourced architecture
from maestro.commands import Command, ExecuteStep, StartBranches, Stop, WaitForInput
from maestro.engine import Engine
from maestro.events import (
    BranchCompleted,
    BranchStarted,
    Event,
    InputReceived,
    InputRequested,
    RunCompleted,
    RunFailed,
    RunPaused,
    RunResumed,
    RunStarted,
    StepCompleted,
    StepFailed,
    StepStarted,
)

# Legacy handlers (deprecated, but still available for backward compatibility)
from maestro.handlers import (
    BranchContext,
    BranchingSignalHandler,
    DefaultSignalHandler,
    MergeStrategy,
    SignalHandler,
    SignalHandlerError,
    SignalResult,
)
from maestro.log import EventLog, InMemoryEventLog
from maestro.merge import DefaultMergeStrategy
from maestro.merge import MergeStrategy as NewMergeStrategy
from maestro.replay import Replayer

# Core types (always available)
from maestro.result import BranchRequest, BranchSpec, StepResult
from maestro.runner import Runner, RunOutcome
from maestro.signals import Signal
from maestro.state import AwaitState, BranchState, RunState
from maestro.step import Step
from maestro.workflow import TickResult, Workflow, WorkflowError

__all__ = [
    # Core types
    "BranchRequest",
    "BranchSpec",
    "Signal",
    "Step",
    "StepResult",
    "TickResult",
    "Workflow",
    "WorkflowError",
    # New event-sourced architecture
    "AwaitState",
    "BranchCompleted",
    "BranchStarted",
    "BranchState",
    "Command",
    "DefaultMergeStrategy",
    "Engine",
    "Event",
    "EventLog",
    "ExecuteStep",
    "InMemoryEventLog",
    "InputReceived",
    "InputRequested",
    "NewMergeStrategy",
    "Replayer",
    "RunCompleted",
    "RunFailed",
    "RunOutcome",
    "RunPaused",
    "RunResumed",
    "Runner",
    "RunStarted",
    "RunState",
    "StartBranches",
    "StepCompleted",
    "StepFailed",
    "StepStarted",
    "Stop",
    "WaitForInput",
    # Legacy (deprecated but available for backward compat)
    "BranchContext",
    "BranchingSignalHandler",
    "DefaultSignalHandler",
    "MergeStrategy",
    "SignalHandler",
    "SignalHandlerError",
    "SignalResult",
]

__version__ = "0.1.0"

# Deprecation warnings for legacy APIs
_DEPRECATED_APIS: dict[str, str] = {
    "BranchingSignalHandler": "Use Engine for signal handling instead.",
    "DefaultSignalHandler": "Use Engine for signal handling instead.",
    "SignalHandler": "Use Engine for signal handling instead.",
    "SignalResult": "Use Event types for workflow state communication.",
}


def __getattr__(name: str) -> Any:
    """Handle deprecated attribute access with warnings."""
    if name in _DEPRECATED_APIS:
        warnings.warn(
            f"{name} is deprecated. {_DEPRECATED_APIS[name]}",
            DeprecationWarning,
            stacklevel=2,
        )
        # Return from handlers module for backward compatibility
        from maestro import handlers

        return getattr(handlers, name)
    raise AttributeError(f"module 'maestro' has no attribute '{name}'")
