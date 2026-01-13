# Sandwich Refactor (Maestro Extraction)

## Overview

Decouple the deterministic workflow engine from business logic by extracting a new library, **maestro**. Refactor dataing to become a "thin" application layer that orchestrates maestro flows using bond agents for intelligence.

### Business Value

- **Separation of Concerns**: "How a workflow runs" (Maestro) vs "What the workflow does" (Dataing)
- **Reusability**: maestro and bond become generic assets usable for other projects
- **Stability**: Core state machine logic can be tested 100% deterministically
- **Testability**: Clear boundaries enable isolated unit testing

### The "Sandwich" Stack

| Layer | Library | Responsibility | Key Objects |
|-------|---------|---------------|-------------|
| Flow (Bottom) | maestro | Deterministic state machine | Workflow, Step, StepResult |
| Brains (Side) | bond | Agent interface, LLM loops | BondAgent, StreamHandlers |
| Logic (Top) | dataing | Business domain | InvestigationContext, domain steps |

## Scope

### In Scope

- Phase 1: Create maestro library with generic protocols
- Phase 2: Refactor dataing to use maestro
- Phase 3: Create BondStep bridge for AI-powered steps
- Phase 4: Delete legacy orchestrator code

### Out of Scope

- Distributed workflow execution
- Step versioning for backward compatibility
- OpenTelemetry integration (future work)
- UI changes

## Architecture

### Package Structure

```
maestro/                    # New package - generic workflow
  src/maestro/
    ├── __init__.py
    ├── step.py             # Step[ContextT, InputT, OutputT] protocol
    ├── result.py           # StepResult[ContextT, OutputT]
    ├── workflow.py         # Workflow engine (tick loop)
    ├── signals.py          # Signal enum (CONTINUE, COMPLETE, FAIL, BRANCH, MERGE)
    └── repository.py       # WorkflowRepository protocol

bond/                       # Existing - generic agent
  src/bond/
    ├── agent.py            # BondAgent (existing)
    └── maestro/            # NEW: Bridge module
        └── bond_step.py    # BondStep base class

dataing/                    # Existing - domain
  src/dataing/
    ├── core/investigation/
    │   ├── context.py      # InvestigationContext (satisfies maestro protocol)
    │   ├── steps/          # Steps implement maestro.Step[InvestigationContext]
    │   ├── flow.py         # NEW: build_investigation_flow()
    │   └── signal_handlers.py  # Domain-specific signal handling
    └── agents/             # Domain agents using bond.BondAgent
```

### Key Interfaces

```python
# maestro/step.py
from typing import Protocol, TypeVar, Generic

ContextT = TypeVar("ContextT")
InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT", covariant=True)

@dataclass(frozen=True)
class StepResult(Generic[ContextT, OutputT]):
    context: ContextT
    signal: Signal
    output: OutputT | None = None
    next_step: str | None = None
    branch_request: BranchRequest | None = None

class Step(Protocol[ContextT, InputT, OutputT]):
    @property
    def name(self) -> str: ...

    async def execute(
        self, context: ContextT, input_data: InputT | None = None
    ) -> StepResult[ContextT, OutputT]: ...

    def can_execute(self, context: ContextT) -> bool: ...
```

### Design Decisions

1. **Protocol-based Step interface**: Use `typing.Protocol` for structural subtyping. Steps don't need to inherit from maestro base classes - they just need to satisfy the protocol.

2. **Generic Context**: `ContextT` is a type parameter. `InvestigationContext` satisfies it by being a frozen Pydantic model with immutable update pattern via `model_copy()`.

3. **Signal subset**: maestro defines core signals (CONTINUE, COMPLETE, FAIL, BRANCH, MERGE). Domain-specific signals like AWAIT_USER become domain signal handlers that produce core signals.

4. **Repository Protocol**: maestro defines `WorkflowRepository[ContextT]` protocol. `InvestigationRepository` implements it by adapting domain methods.

5. **BondStep in bond package**: The bridge between maestro.Step and BondAgent lives in `bond/maestro/` to avoid circular dependencies.

6. **Pluggable merge strategy**: maestro accepts `MergeStrategy[ContextT]` for branch convergence. Dataing provides `InvestigationMergeStrategy`.

## Approach

### Phase 1: Create maestro Library

Create a standalone package with zero dependencies on pydantic-ai or dataing.

**Key Files:**
- `maestro/src/maestro/step.py` - Step protocol and StepResult
- `maestro/src/maestro/signals.py` - Signal enum
- `maestro/src/maestro/workflow.py` - Workflow engine with tick loop
- `maestro/src/maestro/repository.py` - WorkflowRepository protocol
- `maestro/pyproject.toml` - Package definition

### Phase 2: Refactor dataing to use maestro

Update dataing to depend on maestro, migrate steps to new protocol.

**Key Changes:**
- `dataing/src/dataing/core/investigation/steps/protocol.py` - Import from maestro
- All step implementations - Update signatures to use maestro.StepResult
- `dataing/src/dataing/core/investigation/flow.py` - New entry point using maestro.Workflow
- Signal handlers - Adapt to work with maestro's signal system

### Phase 3: Integrate bond for Intelligence

Create the BondStep bridge for AI-powered steps.

**Key Changes:**
- `bond/src/bond/maestro/bond_step.py` - Abstract base class
- Update RecursiveAnalysisStep to use BondStep pattern
- Verify StreamHandlers integration works

### Phase 4: The Great De-Bloat

Delete legacy code now handled by libraries.

**Deleted Files:**
- `dataing/core/investigation/orchestrator/base.py` (replaced by maestro.Workflow)
- `dataing/core/investigation/orchestrator/protocol.py` (replaced by maestro.Step)
- Any custom LLM loop code (bond handles this)

## Quick Commands

```bash
# Test maestro in isolation
cd maestro && uv run pytest tests/ -v

# Test dataing with maestro integration
cd dataing && uv run pytest tests/unit/core/investigation/ -v

# Smoke test: Run a simple workflow
cd maestro && uv run python -c "
from maestro import Workflow, Step, StepResult, Signal

class DummyStep:
    name = 'dummy'
    async def execute(self, ctx, input_data=None):
        return StepResult(context=ctx, signal=Signal.COMPLETE)
    def can_execute(self, ctx): return True

import asyncio
flow = Workflow()
flow.add_step(DummyStep())
result = asyncio.run(flow.run({'start': True}, 'dummy'))
print('Workflow completed:', result)
"

# Type check maestro
cd maestro && uv run mypy src/maestro/ --strict
```

## Technical DoD

- [ ] Three packages: maestro (new), bond (existing), dataing (refactored)
- [ ] No circular dependencies: maestro and bond must not import dataing
- [ ] `pip install maestro-flow` works (local editable install)
- [ ] maestro has zero LLM dependencies (no pydantic-ai, openai, anthropic)
- [ ] Existing dataing integration tests pass
- [ ] dataing codebase reduced by ~20% (excluding new libraries)
- [ ] All Step implementations satisfy maestro.Step protocol (mypy passes)

## Migration Strategy

1. **Incremental**: Phase 2 can wrap legacy steps before full migration
2. **Feature Flag**: `INVESTIGATION_ENGINE=v2` env var to test maestro path
3. **Parallel Run**: Both engines can run in staging for comparison
4. **Rollback**: Feature flag off reverts to legacy orchestrator

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Type erasure in generic context | Steps lose type safety | Use runtime_checkable Protocol + explicit type hints |
| Step dependency injection timing | Steps created without deps | StepFactory pattern preserved, deps injected at construction |
| Signal handler complexity | Domain logic scattered | Centralize in signal_handlers.py with clear extension points |
| Bond agent history persistence | State lost on restart | Document as limitation; history is per-session |
| Big bang migration failure | All steps break at once | Incremental migration with adapter pattern |

## Open Questions

1. Should maestro have built-in retry policies per step, or delegate to steps?
2. Where does branching strategy live - maestro plugin or domain handler?
3. Should maestro's Signal enum be extensible (IntEnum with domain additions)?

## References

- Current orchestrator: `dataing/src/dataing/core/investigation/orchestrator/base.py:22-176`
- Step protocol: `dataing/src/dataing/core/investigation/steps/protocol.py:20-94`
- Signal enum: `dataing/src/dataing/core/investigation/values.py:91-101`
- BondAgent: `bond/src/bond/agent.py:76-291`
- StepRegistry: `dataing/src/dataing/core/investigation/registry.py:15-63`
- Signal handlers: `dataing/src/dataing/core/investigation/orchestrator/signal_handlers.py:20-294`
- InvestigationContext: `dataing/src/dataing/core/investigation/entities.py:20-64`
- Step factory: `dataing/src/dataing/adapters/investigation/step_factory.py:42-127`
