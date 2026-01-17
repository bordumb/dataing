Brutal critique of where you are right now

1) SignalHandler / BranchingSignalHandler is a dead-end abstraction

File: maestro/src/maestro/handlers.py
	•	It’s stateful (_pending_branches, _parent_contexts, _expected_counts) which means:
	•	replay isn’t real
	•	distributed execution becomes a nightmare
	•	correctness depends on runtime object lifetime
	•	It’s async, so “decision logic” is now allowed to do arbitrary I/O. That breaks determinism at the root.

If you’re serious about event-sourcing: delete this file. Don’t “deprecate” it.

2) Your workflow state is implicit

File: maestro/src/maestro/workflow.py

You don’t have a first-class RunState. You have a tick loop + local vars + handler-held state. That means:
	•	you can’t pause/resume cleanly
	•	you can’t replay deterministically
	•	you can’t run the same run across processes safely

3) Signal.MERGE should not exist

File: maestro/src/maestro/signals.py

MERGE is a smell. Merge should be a consequence of branch completion, not something steps “signal” like a control-flow opcode. Keep branching as a signal. Remove MERGE entirely and make merge an engine behavior.

⸻

The best long-term solution (no choices, just do this)

Non-negotiables
	1.	Engine is pure + synchronous
	•	apply(state, event) -> (new_state, next_command)
	•	no await, no side effects, no network, no clocks
	2.	Runner is the only async thing
	•	executes steps, schedules branches, waits for user input
	•	emits events to the log
	3.	Event log is canonical
	•	state is derived from events
	•	“resume” is just “load events → replay → continue”
	4.	Branching state lives in RunState, not in a handler
	5.	Delete “handlers” and any “legacy compatibility”

⸻

What to keep / remove / add

KEEP (but some will be modified)
	•	maestro/src/maestro/step.py (keep Step protocol)
	•	maestro/src/maestro/signals.py (MODIFY: remove MERGE)
	•	maestro/src/maestro/result.py (MODIFY: add explicit “await token” fields + validate)
	•	maestro/src/maestro/workflow.py (REWRITE: becomes a facade / builder, not an orchestrator)

REMOVE
	•	maestro/src/maestro/handlers.py (delete entirely)
	•	maestro/src/maestro/signals.py::Signal.MERGE (delete)

ADD (new core)
	•	maestro/src/maestro/state.py
	•	maestro/src/maestro/events.py
	•	maestro/src/maestro/commands.py
	•	maestro/src/maestro/engine.py
	•	maestro/src/maestro/log.py
	•	maestro/src/maestro/runner.py
	•	maestro/src/maestro/replay.py

⸻

Minimal concepts + code skeleton per file

maestro/src/maestro/state.py

The entire truth of a run.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Generic, TypeVar

ContextT = TypeVar("ContextT")

@dataclass(frozen=True)
class BranchState(Generic[ContextT]):
    merge_step: str
    expected: int
    parent_context: ContextT
    completed: dict[str, ContextT] = field(default_factory=dict)

@dataclass(frozen=True)
class AwaitState:
    token: str
    resume_step: str

@dataclass(frozen=True)
class RunState(Generic[ContextT]):
    run_id: str
    status: Literal["running", "paused", "completed", "failed"]
    context: ContextT
    next_step: str
    seq: int = 0

    branch: BranchState[ContextT] | None = None
    awaiting: AwaitState | None = None
    error: str | None = None


⸻

maestro/src/maestro/events.py

Events are the audit trail + replay input.

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal

@dataclass(frozen=True)
class Event:
    run_id: str
    seq: int

@dataclass(frozen=True)
class RunStarted(Event):
    start_step: str
    context: Any

@dataclass(frozen=True)
class StepCompleted(Event):
    step: str
    context: Any
    signal: str
    next_step: str | None = None
    branch_request: Any | None = None
    await_token: str | None = None
    resume_step: str | None = None

@dataclass(frozen=True)
class StepFailed(Event):
    step: str
    error: str

@dataclass(frozen=True)
class BranchCompleted(Event):
    branch_name: str
    context: Any

@dataclass(frozen=True)
class InputReceived(Event):
    token: str
    data: Any


⸻

maestro/src/maestro/commands.py

Commands are what the engine tells the runner to do.

from dataclasses import dataclass
from typing import Any, Literal

@dataclass(frozen=True)
class Command: ...

@dataclass(frozen=True)
class ExecuteStep(Command):
    step: str
    input_data: Any | None = None

@dataclass(frozen=True)
class StartBranches(Command):
    branch_request: Any  # reuse BranchRequest from result.py

@dataclass(frozen=True)
class WaitForInput(Command):
    token: str

@dataclass(frozen=True)
class Stop(Command):
    status: Literal["completed", "failed"]
    result: Any


⸻

maestro/src/maestro/engine.py

Pure reducer. This is the “kernel”.

Key brutal simplification:
	•	remove MERGE signal
	•	BRANCH implies “engine enters branch-wait mode”; once all branches complete, engine runs merge_step.

from __future__ import annotations
from typing import Any, Tuple
from maestro.state import RunState, BranchState, AwaitState
from maestro.commands import Command, ExecuteStep, StartBranches, WaitForInput, Stop
from maestro.events import RunStarted, StepCompleted, StepFailed, BranchCompleted, InputReceived

class Engine:
    def apply(self, state: RunState, event) -> tuple[RunState, Command]:
        if isinstance(event, RunStarted):
            s = RunState(
                run_id=event.run_id,
                status="running",
                context=event.context,
                next_step=event.start_step,
                seq=event.seq,
            )
            return s, ExecuteStep(step=s.next_step)

        if isinstance(event, StepFailed):
            s = RunState(**{**state.__dict__, "status": "failed", "error": event.error, "seq": event.seq})
            return s, Stop(status="failed", result=event.error)

        if isinstance(event, StepCompleted):
            # AWAIT_USER
            if event.await_token and event.resume_step:
                s = RunState(
                    **{**state.__dict__},
                    status="paused",
                    context=event.context,
                    awaiting=AwaitState(token=event.await_token, resume_step=event.resume_step),
                    seq=event.seq,
                )
                return s, WaitForInput(token=event.await_token)

            # BRANCH
            if event.branch_request is not None:
                br = BranchState(
                    merge_step=event.branch_request.merge_step,
                    expected=len(event.branch_request.branches),
                    parent_context=event.context,
                )
                s = RunState(**{**state.__dict__}, context=event.context, branch=br, seq=event.seq)
                return s, StartBranches(branch_request=event.branch_request)

            # COMPLETE
            if event.signal == "complete":
                s = RunState(**{**state.__dict__}, status="completed", context=event.context, seq=event.seq)
                return s, Stop(status="completed", result=event.context)

            # CONTINUE
            nxt = event.next_step or state.next_step  # runner can compute sequential fallback if you want
            s = RunState(**{**state.__dict__}, context=event.context, next_step=nxt, seq=event.seq)
            return s, ExecuteStep(step=nxt)

        if isinstance(event, BranchCompleted):
            assert state.branch is not None
            completed = dict(state.branch.completed)
            completed[event.branch_name] = event.context

            br = BranchState(
                merge_step=state.branch.merge_step,
                expected=state.branch.expected,
                parent_context=state.branch.parent_context,
                completed=completed,
            )

            # still waiting
            if len(completed) < br.expected:
                s = RunState(**{**state.__dict__}, branch=br, seq=event.seq)
                return s, WaitForInput(token="__internal_branch_wait__")  # or a Noop command type

            # all branches done -> run merge_step next
            merged_input = {
                "parent": br.parent_context,
                "branches": completed,
            }
            s = RunState(**{**state.__dict__}, branch=None, next_step=br.merge_step, seq=event.seq)
            return s, ExecuteStep(step=br.merge_step, input_data=merged_input)

        if isinstance(event, InputReceived):
            assert state.awaiting is not None and event.token == state.awaiting.token
            s = RunState(**{**state.__dict__}, status="running", awaiting=None, next_step=state.awaiting.resume_step, seq=event.seq)
            return s, ExecuteStep(step=s.next_step, input_data=event.data)

        raise RuntimeError(f"Unhandled event type: {type(event)}")

(That WaitForInput("__internal_branch_wait__") is ugly — in real code, add Noop or Yield command.)

⸻

maestro/src/maestro/log.py

Deterministic event store (in-memory now, pluggable later).

from dataclasses import dataclass, field
from typing import Iterable, List
from maestro.events import Event

@dataclass
class InMemoryEventLog:
    events: list[Event] = field(default_factory=list)

    def append(self, e: Event) -> None:
        self.events.append(e)

    def read(self) -> list[Event]:
        return list(self.events)


⸻

maestro/src/maestro/replay.py

Your “time machine”.

from maestro.engine import Engine
from maestro.state import RunState
from maestro.commands import Command

def replay(engine: Engine, events) -> tuple[RunState, Command]:
    state = None
    cmd = None
    for e in events:
        if state is None:
            # you can bootstrap with a dummy state or treat RunStarted specially
            from maestro.state import RunState
            state = RunState(run_id=e.run_id, status="running", context=None, next_step="", seq=0)
        state, cmd = engine.apply(state, e)
    assert state is not None and cmd is not None
    return state, cmd

⸻

The fixes you should make (prioritized, concrete)

A. Delete dead abstractions
	•	Delete maestro/src/maestro/handlers.py
	•	Remove Signal.MERGE from maestro/src/maestro/signals.py
	•	Remove any merge “signal handling” logic entirely

B. Make state explicit + serializable
	•	Add maestro/src/maestro/state.py with RunState, BranchState, AwaitState
	•	Ensure state is JSON-serializable (or provide encode/decode helpers)

C. Make control flow event-driven
	•	Add events.py, commands.py, engine.py, log.py, replay.py, runner.py
	•	Engine must be pure and total (every event type handled)

D. Tighten StepResult to support pause/resume + branch determinism

File: maestro/src/maestro/result.py
	•	Add fields for AWAIT_USER: await_token: str | None, resume_step: str | None
	•	Validate:
	•	BRANCH requires branch_request
	•	AWAIT_USER requires (await_token, resume_step)
	•	FAIL requires error
	•	Consider removing output from core semantics (keep it for UX) — workflow correctness should depend on context + events.

E. Rewrite workflow.py as a facade

File: maestro/src/maestro/workflow.py
	•	It should mostly:
	•	register steps
	•	choose a start step
	•	construct runner+engine+log
	•	call Runner.run()
	•	No branching logic living here. No signal handlers.

F. Tests that prove you actually got the benefits
	•	Determinism: same events ⇒ same final state
	•	Replay matches live run
	•	Branch completion order doesn’t change outcome (if merge is deterministic)
	•	Pause/resume with InputReceived

G. Small but important polish
	•	Add monotonic seq enforcement in log append
	•	Add run_id everywhere, always
	•	Add a tiny Noop command so you don’t hack WaitForInput("__internal...")
