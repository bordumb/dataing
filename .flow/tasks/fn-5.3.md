# fn-5.3 Port Signal Handling to Maestro

## Description
Port signal handling logic to maestro as an extensible plugin system.

## Implementation

1. Define `SignalHandler[ContextT]` protocol:
   ```python
   class SignalHandler(Protocol[ContextT]):
       async def handle(
           self,
           signal: Signal,
           context: ContextT,
           result: StepResult,
           workflow: Workflow,
       ) -> ContextT | None:
           """Handle signal, return new context or None to halt."""
           ...
   ```

2. Create `DefaultSignalHandler` with basic implementations:
   - `handle_continue()` - Return context, workflow picks next step
   - `handle_complete()` - Return context, signal halt
   - `handle_fail()` - Raise WorkflowError

3. Create `BranchingSignalHandler` extending default:
   - `handle_branch()` - Create child workflows from BranchRequest
   - `handle_merge()` - Check for convergence, trigger merge callback

4. Add `Workflow.set_signal_handler(handler)` for customization.

5. Define `MergeStrategy[ContextT]` protocol:
   - `merge(parent_context, child_contexts) -> ContextT`

## Key Files
- New: `maestro/src/maestro/handlers.py`
- Reference: `dataing/src/dataing/core/investigation/orchestrator/signal_handlers.py:20-294`
- Reference: `dataing/src/dataing/core/investigation/orchestrator/merge.py:15-75`
## Acceptance
- [ ] `SignalHandler` protocol defined
- [ ] `DefaultSignalHandler` handles CONTINUE, COMPLETE, FAIL
- [ ] `BranchingSignalHandler` handles BRANCH, MERGE
- [ ] `Workflow.set_signal_handler()` allows custom handlers
- [ ] `MergeStrategy` protocol defined for branch convergence
- [ ] BRANCH creates child workflow contexts
- [ ] MERGE waits for all children before triggering merge
- [ ] Signal handlers are async
- [ ] Unit test: BRANCH signal creates child contexts
- [ ] Unit test: MERGE with custom strategy merges children
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
