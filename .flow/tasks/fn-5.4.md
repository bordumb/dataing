# fn-5.4 Update InvestigationContext for Maestro

## Description
Make InvestigationContext compatible with maestro's generic context requirements.

## Implementation

1. Verify InvestigationContext satisfies maestro requirements:
   - Is a frozen Pydantic model (immutable)
   - Has `model_copy(update={...})` for updates
   - Is JSON serializable via `model_dump(mode="json")`

2. Create `ContextProtocol` type alias in dataing if needed:
   ```python
   # dataing/src/dataing/core/investigation/types.py
   from maestro import Step, StepResult

   InvestigationStep = Step[InvestigationContext, Any, Any]
   InvestigationResult = StepResult[InvestigationContext, Any]
   ```

3. Remove any hard-coded `next_step` logic from context itself - this belongs in step results.

4. Add any missing fields for maestro integration (if needed).

## Key Files
- Modify: `dataing/src/dataing/core/investigation/entities.py:20-64`
- New: `dataing/src/dataing/core/investigation/types.py` (optional)
- Reference: `maestro/src/maestro/step.py`
## Acceptance
- [ ] InvestigationContext is compatible with maestro `ContextT`
- [ ] `model_copy(update={...})` pattern works with maestro steps
- [ ] `model_dump(mode="json")` serializes correctly
- [ ] Type aliases created for step typing convenience
- [ ] No circular imports between dataing and maestro
- [ ] `mypy` passes with maestro types used in dataing
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
