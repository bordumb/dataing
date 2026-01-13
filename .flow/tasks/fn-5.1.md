# fn-5.1 Define Maestro Core Protocols

## Description
Create the maestro package with core protocols for generic step-based workflows.

## Implementation

1. Create `maestro/` package structure:
   ```
   maestro/
     src/maestro/
       __init__.py
       step.py
       result.py
       signals.py
     pyproject.toml
     tests/
   ```

2. Define `Signal` enum in `signals.py`:
   - CONTINUE: Proceed to next step
   - COMPLETE: Workflow finished successfully
   - FAIL: Workflow failed
   - BRANCH: Create child workflows
   - MERGE: Await branch convergence

3. Define `StepResult[ContextT, OutputT]` in `result.py`:
   - `context: ContextT` - Updated context
   - `signal: Signal` - Control flow signal
   - `output: OutputT | None` - Step output
   - `next_step: str | None` - Explicit next step name
   - `branch_request: BranchRequest | None` - For BRANCH signal

4. Define `Step` protocol in `step.py`:
   - `name: str` property
   - `async execute(context, input_data) -> StepResult`
   - `can_execute(context) -> bool`

5. Use `typing.Protocol` with `@runtime_checkable` for structural subtyping.

## Key Files
- New: `maestro/src/maestro/step.py`
- New: `maestro/src/maestro/result.py`
- New: `maestro/src/maestro/signals.py`
- Reference: `dataing/src/dataing/core/investigation/steps/protocol.py:20-94`
- Reference: `dataing/src/dataing/core/investigation/values.py:91-101`
## Acceptance
- [ ] `maestro/` package exists with `pyproject.toml`
- [ ] `pip install -e ./maestro` works
- [ ] `Signal` enum has 5 values: CONTINUE, COMPLETE, FAIL, BRANCH, MERGE
- [ ] `StepResult` is a frozen dataclass with generic type parameters
- [ ] `Step` is a `typing.Protocol` (not ABC)
- [ ] `Step` is `@runtime_checkable`
- [ ] `mypy maestro/src/maestro/ --strict` passes
- [ ] Unit tests cover StepResult creation and Signal usage
- [ ] No dependencies on pydantic-ai, openai, or anthropic
## Done summary
- Created maestro package with core protocols for generic workflows
- Defined Signal enum (CONTINUE, COMPLETE, FAIL, BRANCH, MERGE)
- Defined StepResult[ContextT, OutputT] frozen dataclass with validation
- Defined Step protocol with @runtime_checkable for structural subtyping

Why:
- Decouples workflow engine from domain logic
- Protocol-based design enables structural subtyping (no ABC inheritance required)

Verification:
- 21 unit tests passing
- mypy --strict passes
- pip install -e ./maestro works
- No LLM dependencies (pydantic-ai, openai, anthropic)
## Evidence
- Commits: 5e7555a7747628947063c2eff1567def6c92a7da
- Tests: cd maestro && uv run pytest tests/ -v
- PRs:
