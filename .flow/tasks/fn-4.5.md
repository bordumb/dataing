# fn-4.5 Programmatic branch triggering via request_branch

## Description


Enable the LLM to programmatically spawn child investigations via the `request_branch` tool.

### Branch Triggering Flow

1. LLM calls `request_branch(rationale, filter_condition)`
2. Tool creates filter mask code: `child_df = parent_df.query(filter_condition)`
3. Step returns `StepResult` with `signal=ExecutionSignal.BRANCH` and `branch_requests`
4. Orchestrator's branch handler creates child investigation with filtered DataRegistry

### Changes to StepResult

Extend `backend/src/dataing/core/investigation/steps/protocol.py`:

```python
@dataclass(frozen=True)
class BranchSpec:
    name: str
    filter_condition: str  # NEW: pandas query string
    rationale: str  # NEW: why LLM requested this branch

@dataclass(frozen=True)
class StepResult:
    # Existing fields...
    branch_requests: tuple[BranchSpec, ...] = ()  # For BRANCH signal
```

### Changes to Branch Handler

Modify `backend/src/dataing/core/investigation/orchestrator/signal_handlers.py`:

```python
async def handle_branch(
    result: StepResult,
    snapshot: InvestigationSnapshot,
    repository: InvestigationRepository,
    data_registry: DataRegistry,  # NEW: pass registry
) -> InvestigationSnapshot:
    for branch_spec in result.branch_requests:
        # Create filtered DataRegistry for child
        child_registry = DataRegistry()
        for name in data_registry.list_names():
            parent_df = data_registry.get(name)
            child_df = parent_df.query(branch_spec.filter_condition)
            child_registry.register(child_df, name)

        # Create child investigation with filtered registry
        # ...
```

### Files to Modify

- `backend/src/dataing/core/investigation/steps/protocol.py` - Extend BranchSpec
- `backend/src/dataing/core/investigation/orchestrator/signal_handlers.py` - Filter registry on branch
- `backend/tests/unit/core/investigation/orchestrator/test_signal_handlers.py` - Test branch filtering

### References

- Branch Handler: `core/investigation/orchestrator/signal_handlers.py:166-251`
- BranchSpec: `core/investigation/steps/protocol.py:21-39`
## Acceptance
- [ ] `BranchSpec` extended with `filter_condition` and `rationale` fields
- [ ] Branch handler accepts `DataRegistry` parameter
- [ ] Child branches receive filtered copy of parent's DataRegistry
- [ ] Filter uses pandas `.query()` on all registered DataFrames
- [ ] Invalid filter condition raises descriptive error
- [ ] Unit test: branch creates filtered registry
- [ ] Unit test: multiple branches with different filters
- [ ] mypy --strict passes
- [ ] ruff check passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
