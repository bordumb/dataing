# fn-5.2 Implement Workflow Engine

## Description
Implement the Workflow engine that executes steps in a tick loop.

## Implementation

1. Create `Workflow[ContextT]` class in `workflow.py`:
   - `add_step(step: Step)` - Register a step
   - `async run(initial_context, start_step) -> ContextT` - Execute until completion
   - `async tick(context, current_step) -> TickResult` - Single step execution

2. Implement tick loop logic:
   - Get step by name from registry
   - Check `can_execute()` - skip or fail if false
   - Call `step.execute(context, input_data)`
   - Return TickResult with signal and next context

3. Define `TickResult[ContextT]`:
   - `context: ContextT`
   - `signal: Signal`
   - `next_step: str | None`
   - `branch_request: BranchRequest | None`

4. Handle core signals in run loop:
   - CONTINUE: Get next step from result or sequential order
   - COMPLETE: Exit loop, return context
   - FAIL: Exit loop, raise exception with context

5. BRANCH and MERGE signals should raise NotImplementedError (handled in fn-5.3).

## Key Files
- New: `maestro/src/maestro/workflow.py`
- Reference: `dataing/src/dataing/core/investigation/orchestrator/base.py:22-176`
- Reference: `dataing/src/dataing/core/investigation/orchestrator/types.py:12-21`
## Acceptance
- [ ] `Workflow` class exists with `add_step()` and `run()` methods
- [ ] `tick()` executes a single step and returns TickResult
- [ ] `run()` loops until COMPLETE or FAIL signal
- [ ] Steps can be retrieved by name
- [ ] CONTINUE signal advances to next step
- [ ] COMPLETE signal exits with final context
- [ ] FAIL signal raises WorkflowError with context
- [ ] `can_execute()` returning False is handled (skip or fail configurable)
- [ ] Unit test: 2-step workflow runs to completion
- [ ] Unit test: Step returning FAIL stops workflow
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
