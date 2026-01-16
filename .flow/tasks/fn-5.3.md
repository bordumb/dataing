# fn-5.3 Port Signal Handling to Maistro

## Description
Port signal handling logic to maistro as an extensible plugin system.

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
- New: `maistro/src/maistro/handlers.py`
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
- Added SignalHandler ABC with pluggable signal handling
- Created DefaultSignalHandler for CONTINUE, COMPLETE, FAIL
- Created BranchingSignalHandler for BRANCH/MERGE with MergeStrategy
- Added Workflow.set_signal_handler() for custom handlers

Why:
- Allows domain-specific signal handling without modifying core workflow
- MergeStrategy protocol enables custom branch merging logic

Verification:
- 67 total tests passing (22 new handler tests)
- mypy --strict passes
## Evidence
- Commits: c48c334b624a22720d83c05ca4dd5e5b6cb3cdd7
- Tests: cd maistro && uv run pytest tests/ -v
- PRs:
