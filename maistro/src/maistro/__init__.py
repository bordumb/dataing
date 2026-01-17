"""Maistro: Event-sourced workflow engine.

Maistro provides a deterministic, replayable workflow engine using
event sourcing. Workflows are defined as sequences of Steps that transform
context and emit signals to control flow.

Core concepts:
- Step: A unit of work that transforms context and produces signals
- Signal: Control flow instructions (CONTINUE, COMPLETE, FAIL, BRANCH, AWAIT_USER)
- Engine: Pure reducer (state, event) -> (state, command)
- Runner: Async executor that runs commands and emits events
- Events: Immutable records of what happened during execution

Example:
-------
    ```python
    from maistro import Signal, Step, StepResult, Workflow

    class IncrementStep:
        @property
        def name(self) -> str:
            return "increment"

        async def execute(
            self, context: dict, input_data: None = None
        ) -> StepResult[dict, None]:
            new_ctx = {"counter": context.get("counter", 0) + 1}
            signal = Signal.COMPLETE if new_ctx["counter"] >= 10 else Signal.CONTINUE
            return StepResult(context=new_ctx, signal=signal)

        def can_execute(self, context: dict) -> bool:
            return True

    # Build and run workflow
    workflow = Workflow()
    workflow.add_step(IncrementStep())
    result = await workflow.run({"counter": 0})
    ```

"""

# Commands
from maistro.commands import (
    Command,
    ExecuteStep,
    NoOp,
    StartBranches,
    Stop,
    WaitForInput,
)

# Engine (pure reducer)
from maistro.engine import Engine

# Events
from maistro.events import (
    BranchCompleted,
    BranchesRequested,
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

# Event log
from maistro.log import EventLog, InMemoryEventLog

# Merge strategy
from maistro.merge import DefaultMergeStrategy, MergeStrategy

# Replay
from maistro.replay import Replayer

# Result types
from maistro.result import BranchRequest, BranchSpec, StepResult

# Runner
from maistro.runner import Runner, RunOutcome

# Signals
from maistro.signals import Signal

# State
from maistro.state import AwaitState, BranchState, RunState

# Step protocol
from maistro.step import Step

# Workflow facade
from maistro.workflow import Workflow, WorkflowError

__all__ = [
    # Core types
    "BranchRequest",
    "BranchSpec",
    "Signal",
    "Step",
    "StepResult",
    "Workflow",
    "WorkflowError",
    # Engine and Runner
    "Engine",
    "Runner",
    "RunOutcome",
    # Events
    "BranchCompleted",
    "BranchesRequested",
    "BranchStarted",
    "Event",
    "InputReceived",
    "InputRequested",
    "RunCompleted",
    "RunFailed",
    "RunPaused",
    "RunResumed",
    "RunStarted",
    "StepCompleted",
    "StepFailed",
    "StepStarted",
    # Commands
    "Command",
    "ExecuteStep",
    "NoOp",
    "StartBranches",
    "Stop",
    "WaitForInput",
    # State
    "AwaitState",
    "BranchState",
    "RunState",
    # Event log and replay
    "EventLog",
    "InMemoryEventLog",
    "Replayer",
    # Merge strategy
    "DefaultMergeStrategy",
    "MergeStrategy",
]

__version__ = "0.1.0"
