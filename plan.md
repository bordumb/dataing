
Maestro: Event-Sourced State Machine with Engine/Runner Split

High-level overview

Core idea

Turn Maestro into a deterministic state machine driven by an append-only event log.
	•	Protocol (stable / portable): Step, Signal, StepResult, BranchRequest (+ any “wire” types you commit to).
	•	Engine (pure / deterministic): a reducer:
	•	input: (state, event)
	•	output: (new_state, next_command)
	•	no async, no side effects
	•	Runner (effectful): an async loop that:
	•	asks the Engine for a Command
	•	executes side effects (running a step, spawning branches, waiting for user input)
	•	emits an Event back into the Engine
	•	Event Log (deterministic): record every significant transition (step scheduled/completed, branch spawned/merged, paused/resumed, etc.)
	•	Replay harness: given definition + initial_state + events[], you should deterministically reconstruct final state and validate invariants.

What this buys you
	•	Debuggability: “why did this run do that?” → read the log.
	•	Determinism: reproduce bugs by replaying events.
	•	Rust path later: you rewrite Engine + State + Event/Command enums in Rust, keep Python Runner/Steps.

⸻

Files: keep / remove / add

Keep (but modify)

maestro/src/maestro/signals.py (keep)

Your current Signal enum is fine as a stable protocol.

Small tweak recommended: explicitly separate workflow control vs runner effects. (Not required, but it keeps the Engine honest.)
	•	Keep Signal as the Step contract.
	•	Let Engine translate signals into Commands/Events.

No breaking changes needed.

⸻

maestro/src/maestro/result.py (keep, tighten)

Keep StepResult, BranchRequest, etc. It’s already close to “protocol locked down”.

Add validations:
	•	MERGE shouldn’t be emitted by steps anymore (Engine owns merge).
	•	AWAIT_USER should carry a token (or await_token) so resumption is deterministic.

Minimal change (snippet):

# maestro/src/maestro/result.py
@dataclass(frozen=True)
class StepResult(Generic[ContextT, OutputT]):
    context: ContextT
    signal: Signal
    output: OutputT | None = None
    error: str | None = None
    next_step: str | None = None
    branch_request: BranchRequest | None = None
    await_token: str | None = None  # NEW

    def __post_init__(self) -> None:
        if self.signal == Signal.BRANCH and self.branch_request is None:
            raise ValueError("BRANCH signal requires branch_request")
        if self.signal == Signal.AWAIT_USER and not self.await_token:
            raise ValueError("AWAIT_USER signal requires await_token")


⸻

maestro/src/maestro/step.py (keep)

Keep Step.execute(...) as your effect boundary. That’s exactly what you want long-term.

⸻

maestro/src/maestro/workflow.py (keep, but gut the “brain”)

Workflow stays as the public façade and definition builder, but:
	•	remove tick() as “the engine”
	•	remove orchestration logic from run()
	•	replace with: build definition → create engine → run runner

Workflow becomes:
	•	definition construction (steps + ordering + optional routing)
	•	convenience run() wrapper around Runner
	•	optional resume() wrapper for AWAIT_USER

⸻

Remove (or radically rewrite)

maestro/src/maestro/handlers.py (remove statefulness)

Right now BranchingSignalHandler holds mutable state (_pending_branches, _expected_counts, _parent_contexts), which is exactly what you said you want to eliminate.

You have two good options:

Option A (recommended): replace handlers.py with pure strategies
	•	move merge logic into a pure “merge strategy” module
	•	all “pending branch tracking” moves into RunState

Option B: keep file name but rewrite it as pure functions
	•	no internal dictionaries
	•	only stateless transforms

I’d do Option A and add merge.py.

⸻

Add (new files)

1) maestro/src/maestro/state.py (NEW)

Single source of truth for a run’s state, fully serializable.

# maestro/src/maestro/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

ContextT = TypeVar("ContextT")

RunStatus = Literal["running", "paused", "completed", "failed"]

@dataclass(frozen=True)
class BranchState:
    merge_step: str
    expected: set[str]
    completed: dict[str, Any] = field(default_factory=dict)  # branch_name -> branch_context

@dataclass(frozen=True)
class AwaitState:
    token: str  # deterministic resume key

@dataclass(frozen=True)
class RunState(Generic[ContextT]):
    run_id: str
    status: RunStatus
    context: ContextT

    # what the engine expects next
    current_step: str | None  # None if terminal/paused
    pending_branches: BranchState | None = None
    pending_await: AwaitState | None = None

    # determinism / ordering
    seq: int = 0  # monotonically increasing event counter


⸻

2) maestro/src/maestro/commands.py (NEW)

What the Engine tells the Runner to do.

# maestro/src/maestro/commands.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal

@dataclass(frozen=True)
class Command: ...

@dataclass(frozen=True)
class ExecuteStep(Command):
    step_name: str
    input_data: Any | None = None

@dataclass(frozen=True)
class StartBranches(Command):
    branch_request: Any  # BranchRequest (imported), kept Any to avoid circulars in snippet

@dataclass(frozen=True)
class WaitForInput(Command):
    token: str

@dataclass(frozen=True)
class Stop(Command):
    status: Literal["completed", "failed"]
    final_context: Any | None = None
    error: str | None = None


⸻

3) maestro/src/maestro/events.py (NEW)

Events are facts appended to the log.

# maestro/src/maestro/events.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal

@dataclass(frozen=True)
class Event:
    seq: int

@dataclass(frozen=True)
class RunStarted(Event):
    start_step: str

@dataclass(frozen=True)
class StepCompleted(Event):
    step_name: str
    step_result: Any  # StepResult

@dataclass(frozen=True)
class StepFailed(Event):
    step_name: str
    error: str

@dataclass(frozen=True)
class BranchesStarted(Event):
    merge_step: str
    branch_names: list[str]

@dataclass(frozen=True)
class BranchCompleted(Event):
    merge_step: str
    branch_name: str
    branch_context: Any

@dataclass(frozen=True)
class InputRequested(Event):
    token: str

@dataclass(frozen=True)
class InputReceived(Event):
    token: str
    data: Any

(You can add RunCompleted / RunFailed, but it’s also fine to derive those from state + last event.)

⸻

4) maestro/src/maestro/log.py (NEW)

A deterministic event log (in-memory first), plus a single allocator for seq.

# maestro/src/maestro/log.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from maestro.events import Event

T = TypeVar("T", bound=Event)

@dataclass
class InMemoryEventLog:
    _events: list[Event] = field(default_factory=list)
    _next_seq: int = 1

    def append(self, event: Event) -> Event:
        # enforce monotonic seq assignment
        object.__setattr__(event, "seq", self._next_seq)  # or create new event with seq
        self._events.append(event)
        self._next_seq += 1
        return event

    def events(self) -> list[Event]:
        return list(self._events)

Note: In “real” code, don’t mutate frozen dataclasses; instead create events without seq and stamp them in append() by returning a new event instance. Keep the snippet concise; implement correctly.

⸻

5) maestro/src/maestro/merge.py (NEW)

Pure merge strategies (what handlers.py wanted to be).

# maestro/src/maestro/merge.py
from __future__ import annotations
from typing import Any, Protocol

class MergeStrategy(Protocol):
    def merge(self, parent_context: Any, branch_contexts: dict[str, Any]) -> Any: ...

class DefaultMergeStrategy:
    def merge(self, parent_context: Any, branch_contexts: dict[str, Any]) -> Any:
        # placeholder: last write wins; you’ll likely domain-specialize this
        return {**(parent_context if isinstance(parent_context, dict) else {}), **branch_contexts}


⸻

6) maestro/src/maestro/engine.py (NEW)

The deterministic reducer. This replaces Workflow.tick + all handler state.

Key rule: Engine only changes state by applying Events.

# maestro/src/maestro/engine.py
from __future__ import annotations
from dataclasses import replace
from typing import Any, Generic, TypeVar

from maestro.commands import Command, ExecuteStep, StartBranches, Stop, WaitForInput
from maestro.events import (
    BranchCompleted, BranchesStarted, Event, InputReceived, InputRequested,
    RunStarted, StepCompleted, StepFailed,
)
from maestro.result import StepResult
from maestro.signals import Signal
from maestro.state import AwaitState, BranchState, RunState
from maestro.merge import MergeStrategy

ContextT = TypeVar("ContextT")

class Engine(Generic[ContextT]):
    def __init__(self, step_order: list[str], merge_strategy: MergeStrategy):
        self._step_order = step_order
        self._merge = merge_strategy

    def init(self, run_id: str, context: ContextT, start_step: str) -> tuple[RunState[ContextT], Command, Event]:
        state = RunState(run_id=run_id, status="running", context=context, current_step=start_step, seq=0)
        ev = RunStarted(seq=0, start_step=start_step)
        cmd = ExecuteStep(step_name=start_step)
        return state, cmd, ev

    def apply(self, state: RunState[ContextT], event: Event) -> tuple[RunState[ContextT], Command]:
        # bump seq deterministically based on the event
        state = replace(state, seq=event.seq)

        if isinstance(event, RunStarted):
            return state, ExecuteStep(step_name=event.start_step)

        if isinstance(event, StepCompleted):
            return self._on_step_completed(state, event.step_name, event.step_result)

        if isinstance(event, StepFailed):
            failed = replace(state, status="failed", current_step=None)
            return failed, Stop(status="failed", error=event.error)

        if isinstance(event, BranchesStarted):
            bs = BranchState(
                merge_step=event.merge_step,
                expected=set(event.branch_names),
                completed={},
            )
            return replace(state, pending_branches=bs), StartBranches(branch_request=None)  # runner already has request

        if isinstance(event, BranchCompleted):
            bs = state.pending_branches
            if bs is None or bs.merge_step != event.merge_step:
                return replace(state, status="failed", current_step=None), Stop(status="failed", error="unexpected branch result")

            completed = dict(bs.completed)
            completed[event.branch_name] = event.branch_context
            bs2 = replace(bs, completed=completed)

            if set(completed.keys()) == bs2.expected:
                merged_ctx = self._merge.merge(state.context, completed)
                # after merge, go to merge_step (or next after merge_step—your call; pick one and lock it down)
                new_state = replace(state, context=merged_ctx, pending_branches=None, current_step=bs2.merge_step)
                return new_state, ExecuteStep(step_name=bs2.merge_step)

            return replace(state, pending_branches=bs2), WaitForInput(token="__internal_wait__")  # or a NoOp command

        if isinstance(event, InputRequested):
            paused = replace(state, status="paused", pending_await=AwaitState(token=event.token), current_step=None)
            return paused, WaitForInput(token=event.token)

        if isinstance(event, InputReceived):
            if state.pending_await is None or state.pending_await.token != event.token:
                return replace(state, status="failed", current_step=None), Stop(status="failed", error="unexpected input token")
            # resume: decide what step to run next; simplest: store “resume_step” in AwaitState if needed
            resumed = replace(state, status="running", pending_await=None, current_step=self._step_order[0])
            return resumed, ExecuteStep(step_name=resumed.current_step)

        return replace(state, status="failed", current_step=None), Stop(status="failed", error="unhandled event")

    def _on_step_completed(self, state: RunState[ContextT], step_name: str, result: StepResult) -> tuple[RunState[ContextT], Command]:
        # update context first
        state = replace(state, context=result.context)

        if result.signal == Signal.COMPLETE:
            done = replace(state, status="completed", current_step=None)
            return done, Stop(status="completed", final_context=result.context)

        if result.signal == Signal.FAIL:
            failed = replace(state, status="failed", current_step=None)
            return failed, Stop(status="failed", error=result.error or "step failed")

        if result.signal == Signal.AWAIT_USER:
            token = result.await_token  # validated in StepResult
            return state, WaitForInput(token=token)

        if result.signal == Signal.BRANCH:
            br = result.branch_request  # validated
            names = [b.name for b in br.branches]
            # engine moves into “pending branches”; runner will actually start them
            bs = BranchState(merge_step=br.merge_step, expected=set(names), completed={})
            new_state = replace(state, pending_branches=bs, current_step=None)
            # runner will use the real BranchRequest; command includes it
            return new_state, StartBranches(branch_request=br)

        # CONTINUE
        next_step = result.next_step or self._default_next(step_name)
        if next_step is None:
            done = replace(state, status="completed", current_step=None)
            return done, Stop(status="completed", final_context=state.context)
        return replace(state, current_step=next_step), ExecuteStep(step_name=next_step)

    def _default_next(self, step_name: str) -> str | None:
        try:
            i = self._step_order.index(step_name)
        except ValueError:
            return None
        return self._step_order[i + 1] if i + 1 < len(self._step_order) else None

Two important “one-shot” decisions to lock down:
	1.	When branches complete, does Engine run merge_step next, or “continue after merge_step”?
Pick one and make it the invariant. (Above: it executes merge_step.)
	2.	AWAIT_USER resume semantics: what step resumes?
Either:

	•	store resume_step in AwaitState, or
	•	treat “input received” as an input into a known step (eg on_user_input)
Pick one and lock it down.

⸻

7) maestro/src/maestro/runner.py (NEW)

Executes Commands, turns outcomes into Events, appends to log, feeds Engine.

# maestro/src/maestro/runner.py
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from maestro.commands import Command, ExecuteStep, StartBranches, Stop, WaitForInput
from maestro.events import (
    BranchCompleted, InputRequested, StepCompleted, StepFailed,
)
from maestro.log import InMemoryEventLog
from maestro.engine import Engine
from maestro.result import BranchRequest
from maestro.step import Step
from maestro.state import RunState

ContextT = TypeVar("ContextT")

@dataclass(frozen=True)
class RunOutcome(Generic[ContextT]):
    status: str  # "completed" | "failed" | "paused"
    context: ContextT | None = None
    error: str | None = None
    await_token: str | None = None
    events: list[Any] | None = None

class Runner(Generic[ContextT]):
    def __init__(self, engine: Engine[ContextT], steps: dict[str, Step], log: InMemoryEventLog | None = None):
        self.engine = engine
        self.steps = steps
        self.log = log or InMemoryEventLog()

    async def run(self, run_id: str, context: ContextT, start_step: str) -> RunOutcome[ContextT]:
        state, cmd, ev0 = self.engine.init(run_id, context, start_step)
        # append RunStarted properly in real code
        # state, cmd = self.engine.apply(state, self.log.append(ev0))

        while True:
            if isinstance(cmd, ExecuteStep):
                step = self.steps[cmd.step_name]
                try:
                    if hasattr(step, "can_execute") and not await step.can_execute(state.context):
                        # treat as failure or skip; choose and lock down
                        raise RuntimeError(f"step cannot execute: {cmd.step_name}")
                    result = await step.execute(state.context, cmd.input_data)
                    ev = StepCompleted(seq=0, step_name=cmd.step_name, step_result=result)
                    ev = self.log.append(ev)
                    state, cmd = self.engine.apply(state, ev)
                except Exception as e:
                    ev = StepFailed(seq=0, step_name=cmd.step_name, error=str(e))
                    ev = self.log.append(ev)
                    state, cmd = self.engine.apply(state, ev)

            elif isinstance(cmd, StartBranches):
                br: BranchRequest = cmd.branch_request
                # Spawn child runs. Decide: sequential or parallel. Parallel is usually correct.
                async def run_branch(spec):
                    # each branch gets a new run_id; you can embed parent
                    child = Runner(self.engine, self.steps)  # or a child-engine; usually same definition
                    outcome = await child.run(f"{state.run_id}:{spec.name}", state.context, br.child_start_step or start_step)
                    if outcome.status != "completed":
                        raise RuntimeError(f"branch failed: {spec.name} ({outcome.error})")
                    return spec.name, outcome.context

                results = await asyncio.gather(*(run_branch(spec) for spec in br.branches))
                for name, ctx in results:
                    ev = BranchCompleted(seq=0, merge_step=br.merge_step, branch_name=name, branch_context=ctx)
                    ev = self.log.append(ev)
                    state, cmd = self.engine.apply(state, ev)

            elif isinstance(cmd, WaitForInput):
                # Pause and return token to caller (API/UI can resume later)
                token = cmd.token
                ev = InputRequested(seq=0, token=token)
                self.log.append(ev)
                return RunOutcome(status="paused", await_token=token, events=self.log.events())

            elif isinstance(cmd, Stop):
                if cmd.status == "failed":
                    return RunOutcome(status="failed", error=cmd.error, events=self.log.events())
                return RunOutcome(status="completed", context=cmd.final_context, events=self.log.events())

            else:
                return RunOutcome(status="failed", error=f"unknown command: {cmd}", events=self.log.events())

(Again: snippets are intentionally compact—implement correctly in real code.)

⸻

8) maestro/src/maestro/replay.py (NEW)

Deterministically rebuild final state from events.

# maestro/src/maestro/replay.py
from __future__ import annotations
from typing import Any, TypeVar, Generic

from maestro.engine import Engine
from maestro.state import RunState

ContextT = TypeVar("ContextT")

class Replayer(Generic[ContextT]):
    def __init__(self, engine: Engine[ContextT]):
        self.engine = engine

    def replay(self, initial_state: RunState[ContextT], events: list[Any]) -> RunState[ContextT]:
        state = initial_state
        cmd = None
        for ev in events:
            state, cmd = self.engine.apply(state, ev)
        return state

Replay test harness invariant: if you run a real workflow and capture events, replay should end in the same terminal state + context.

⸻

What workflow.py becomes (public API preserved)

Your current Workflow is good ergonomically; keep it.

New responsibilities:
	•	store steps: dict[name, Step]
	•	store step_order: list[str]
	•	run() uses Engine+Runner internally
	•	optionally expose run_until_pause() and resume(await_token, data) later for APIs

Minimal shape:

# maestro/src/maestro/workflow.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from maestro.engine import Engine
from maestro.merge import DefaultMergeStrategy
from maestro.runner import Runner
from maestro.step import Step

ContextT = TypeVar("ContextT")

@dataclass
class Workflow(Generic[ContextT]):
    steps: dict[str, Step]
    step_order: list[str]
    start_step: str | None = None

    def add_step(self, name: str, step: Step, is_start: bool = False) -> None:
        self.steps[name] = step
        self.step_order.append(name)
        if is_start or self.start_step is None:
            self.start_step = name

    async def run(self, context: ContextT) -> ContextT:
        if not self.start_step:
            raise ValueError("No start step defined")

        engine = Engine(step_order=self.step_order, merge_strategy=DefaultMergeStrategy())
        runner = Runner(engine=engine, steps=self.steps)
        outcome = await runner.run(run_id="run_1", context=context, start_step=self.start_step)

        if outcome.status == "completed":
            return outcome.context  # type: ignore
        raise RuntimeError(outcome.error or "workflow failed/paused")


⸻

What to do with handlers.py

Remove BranchingSignalHandler entirely

It becomes redundant because:
	•	“pending branches” is now state, not hidden mutable handler data
	•	“merge behavior” is now pure (merge.py)

You can keep a thin compatibility layer if you want, but the clean move is:
	•	delete handlers.py
	•	replace with merge.py (+ maybe routing.py later if you add rich routing)

⸻

Tests to add (this is where you’ll feel the payoff)

Add these under maestro/tests/:

test_engine_determinism.py
	•	apply same event sequence twice → identical state
	•	out-of-order / unexpected events → fail deterministically

test_replay_matches_live_run.py
	•	run real workflow with deterministic steps
	•	capture events
	•	replay events → same terminal context

test_branch_merge.py
	•	step emits BRANCH with N branches
	•	branches complete
	•	merge produces correct context
	•	merge_step executed next (or whatever invariant you chose)

test_await_user_pause_resume.py
	•	step emits AWAIT_USER with token
	•	runner returns paused outcome
	•	feed InputReceived event → resumes correctly

⸻

Summary of the “one-shot” decisions to lock down now

If you lock these down, you’ll thank yourself later (and it makes Rust rewrite trivial):
	1.	Branch semantics

	•	BranchRequest defines: branches[], merge_step, optional child_start_step
	•	Engine tracks completion in RunState.pending_branches
	•	Merge strategy is pure and deterministic
	•	Post-merge routing: execute merge_step next (or “continue after merge_step”) — pick one.

	2.	Await-user semantics

	•	AWAIT_USER carries an explicit await_token
	•	Runner halts and returns paused(await_token=...)
	•	Resume is implemented as an InputReceived(token, data) event
	•	Engine uses a deterministic rule to pick the resume step (store resume_step in state, or route to a fixed “on_user_input” step)

	3.	Event log is canonical

	•	State can always be derived by replaying events
	•	Engine never mutates state without an event
