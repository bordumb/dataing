# fn-15: Maistro Event-Sourced State Machine

## Summary

This epic transformed Maistro from an imperative workflow executor into a **deterministic event-sourced state machine**. The architecture now separates pure state transitions (Engine) from effectful execution (Runner).

## What Was Built

### New Maistro Architecture

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
| `maistro/src/maistro/state.py` | `RunState`, `BranchState`, `AwaitState` immutable state types |
| `maistro/src/maistro/commands.py` | `ExecuteStep`, `StartBranches`, `WaitForInput`, `Stop` command types |
| `maistro/src/maistro/events.py` | Complete event catalog (11 event types) |
| `maistro/src/maistro/log.py` | `EventLog` protocol + `InMemoryEventLog` implementation |
| `maistro/src/maistro/merge.py` | `MergeStrategy` protocol for branch result aggregation |
| `maistro/src/maistro/engine.py` | Pure reducer: `(state, event) -> (state, command)` |
| `maistro/src/maistro/runner.py` | Async generator yielding events |
| `maistro/src/maistro/replay.py` | Deterministic state reconstruction from events |

### Modified Files

| File | Changes |
|------|---------|
| `maistro/src/maistro/result.py` | Added `await_token` and `context_update` to `StepResult` |
| `maistro/src/maistro/workflow.py` | Refactored as facade over Engine+Runner |
| `maistro/src/maistro/__init__.py` | Updated exports for new architecture |
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
- `maistro/tests/` - 100% pass (includes new determinism and replay tests)
- `bond/tests/` - 100% pass
- `dataing/tests/` - 1378 passed, 37 skipped
- `dataing-ee/tests/` - 100% pass

## Commands

```bash
# Run all maistro tests
uv run pytest maistro/tests/ -v

# Run dataing tests
uv run pytest dataing/tests/ -v

# Type check
uv run mypy maistro/src/maistro/ --strict

# Full test suite
just test
```

## Commits

| Commit | Description |
|--------|-------------|
| `bec1d6a0` | feat(maistro): add state.py with RunState, BranchState, AwaitState |
| `59da620b` | feat(maistro): add commands.py with Command types |
| `df36d40d` | feat(maistro): add events.py with complete event catalog |
| `24935bc0` | feat(maistro): add log.py with EventLog protocol |
| `82a5b1d1` | feat(maistro): add merge.py with MergeStrategy protocol |
| `3748dac9` | feat(maistro): add await_token and context_update to StepResult |
| `6da24105` | feat(maistro): add engine.py with pure reducer Engine class |
| `da7b7bfa` | feat(maistro): add runner.py with async Runner class |
| `306e1f79` | feat(maistro): add replay.py with Replayer class |
| `99dde836` | feat(maistro): refactor workflow.py as facade over Engine+Runner |
| `917c0e60` | feat(dataing): migrate flow.py to new maistro Engine/Runner architecture |
| `ba66e6da` | feat(maistro): update __init__.py exports |
| `bc602cdf` | feat(maistro): add determinism and replay tests |
| `b35c2877` | fix(ci): run tests per-package to avoid conftest conflicts |
| `e832b063` | fix(tests): update dataing tests for API changes |
| `483d269d` | fix(tests): fix remaining dataing test failures |

## Branch

`fn-15` - Ready for PR to main
