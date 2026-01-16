# fn-15: Maestro Event-Sourced State Machine

## Summary

This epic transformed Maestro from an imperative workflow executor into a **deterministic event-sourced state machine**. The architecture now separates pure state transitions (Engine) from effectful execution (Runner).

## What Was Built

### New Maestro Architecture

```
                    +---------+
                    |  Step   |  (Protocol - unchanged)
                    +---------+
                         ^
                         |
+----------+      +------+------+      +----------+
|  Events  | ---> |   Engine    | ---> | Commands |
+----------+      | (pure/sync) |      +----------+
     ^            +-------------+            |
     |                                       v
     |            +-------------+      +----------+
     +----------- |   Runner    | <--- | Run Loop |
                  | (async/gen) |      +----------+
                  +------+------+
                         |
                  +------v------+
                  |  EventLog   |
                  +-------------+
```

### New Files Created

| File | Purpose |
|------|---------|
| `maestro/src/maestro/state.py` | `RunState`, `BranchState`, `AwaitState` immutable state types |
| `maestro/src/maestro/commands.py` | `ExecuteStep`, `StartBranches`, `WaitForInput`, `Stop` command types |
| `maestro/src/maestro/events.py` | Complete event catalog (11 event types) |
| `maestro/src/maestro/log.py` | `EventLog` protocol + `InMemoryEventLog` implementation |
| `maestro/src/maestro/merge.py` | `MergeStrategy` protocol for branch result aggregation |
| `maestro/src/maestro/engine.py` | Pure reducer: `(state, event) -> (state, command)` |
| `maestro/src/maestro/runner.py` | Async generator yielding events |
| `maestro/src/maestro/replay.py` | Deterministic state reconstruction from events |

### Modified Files

| File | Changes |
|------|---------|
| `maestro/src/maestro/result.py` | Added `await_token` and `context_update` to `StepResult` |
| `maestro/src/maestro/workflow.py` | Refactored as facade over Engine+Runner |
| `maestro/src/maestro/__init__.py` | Updated exports for new architecture |
| `dataing/src/dataing/core/investigation/flow.py` | Migrated to new Engine/Runner architecture |

## Key Design Decisions

1. **Deterministic Branch Completion Order**: Branch results are emitted in alphabetical order by branch name, ensuring reproducible event sequences across machines.

2. **Steps Report Facts, Engine Decides Routing**: Steps return `await_token` only; Engine computes `resume_step` using workflow structure.

3. **Engine.apply() Takes Events Only**: Runner translates runtime facts into Events. Engine is pure and never sees raw exceptions.

4. **Context Updates in Events**: Events store context deltas, not full contexts, keeping logs lightweight.

## Benefits

- **Debuggability**: "Why did this run do X?" becomes "read the event log"
- **Determinism**: Reproduce any bug by replaying events
- **Rust migration path**: Engine + State + Events can be rewritten in Rust
- **Testability**: Engine is pure, making unit tests trivial

## Test Coverage

All tests pass:
- `maestro/tests/` - 100% pass (includes new determinism and replay tests)
- `bond/tests/` - 100% pass
- `dataing/tests/` - 1378 passed, 37 skipped
- `dataing-ee/tests/` - 100% pass

## Commands

```bash
# Run all maestro tests
uv run pytest maestro/tests/ -v

# Run dataing tests
uv run pytest dataing/tests/ -v

# Type check
uv run mypy maestro/src/maestro/ --strict

# Full test suite
just test
```

## Commits

| Commit | Description |
|--------|-------------|
| `bec1d6a0` | feat(maestro): add state.py with RunState, BranchState, AwaitState |
| `59da620b` | feat(maestro): add commands.py with Command types |
| `df36d40d` | feat(maestro): add events.py with complete event catalog |
| `24935bc0` | feat(maestro): add log.py with EventLog protocol |
| `82a5b1d1` | feat(maestro): add merge.py with MergeStrategy protocol |
| `3748dac9` | feat(maestro): add await_token and context_update to StepResult |
| `6da24105` | feat(maestro): add engine.py with pure reducer Engine class |
| `da7b7bfa` | feat(maestro): add runner.py with async Runner class |
| `306e1f79` | feat(maestro): add replay.py with Replayer class |
| `99dde836` | feat(maestro): refactor workflow.py as facade over Engine+Runner |
| `917c0e60` | feat(dataing): migrate flow.py to new maestro Engine/Runner architecture |
| `ba66e6da` | feat(maestro): update __init__.py exports |
| `bc602cdf` | feat(maestro): add determinism and replay tests |
| `b35c2877` | fix(ci): run tests per-package to avoid conftest conflicts |
| `e832b063` | fix(tests): update dataing tests for API changes |
| `483d269d` | fix(tests): fix remaining dataing test failures |

## Branch

`fn-15` - Ready for PR to main
