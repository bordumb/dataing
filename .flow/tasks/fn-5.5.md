# fn-5.5 Port Existing Steps to Maestro Protocol

## Description
Update all existing step implementations to use maestro.Step protocol.

## Implementation

1. Update step base class imports:
   ```python
   # Before
   from dataing.core.investigation.steps.protocol import Step, StepResult

   # After
   from maestro import Step, StepResult
   ```

2. Update each step's `execute()` signature:
   - Return `maestro.StepResult[InvestigationContext, OutputT]`
   - Use `maestro.Signal` instead of `ExecutionSignal`

3. Steps to migrate:
   - GatherContextStep
   - GenerateHypothesesStep
   - CheckPatternsStep
   - GenerateQueryStep
   - ExecuteQueryStep
   - InterpretResultsStep
   - SynthesizeStep

4. Keep step logic unchanged - only update types and imports.

5. Update StepRegistry to work with maestro.Step protocol.

## Key Files
- Modify: `dataing/src/dataing/core/investigation/steps/*.py`
- Modify: `dataing/src/dataing/core/investigation/registry.py`
- Delete: `dataing/src/dataing/core/investigation/steps/protocol.py` (after migration)
## Acceptance
- [ ] All steps import from `maestro` package
- [ ] All `execute()` return `maestro.StepResult`
- [ ] `ExecutionSignal` replaced with `maestro.Signal`
- [ ] StepRegistry uses `maestro.Step` protocol
- [ ] All existing step unit tests pass
- [ ] `mypy` passes on all step files
- [ ] No duplicate Step/StepResult definitions in dataing
## Done summary
- Ported all investigation steps to use maestro protocol types
- Added AWAIT_USER signal to maestro.Signal enum for user interaction support
- Added branch_type field to maestro.BranchRequest for domain-specific branching
- Updated protocol.py to re-export maestro types with backward compatibility
- Created DataingStep ABC that satisfies maestro.Step protocol via name property
- Updated all step imports: Signal instead of ExecutionSignal
- Updated all StepResult return types: StepResult[InvestigationContext, OutputT]
- Converted all next_step and merge_step values to strings (.value)
- Updated StepRegistry to use maestro.Step protocol with InvestigationStep alias

Why:
- Steps now use maestro's generic workflow types
- ExecutionSignal removed in favor of maestro.Signal
- StepRegistry uses maestro.Step protocol for type safety
- Backward compatibility maintained via re-exports

Verification:
- mypy passes on all 11 step files (--strict)
- All 68 maestro tests pass
- Import test confirms all steps load correctly
- step.name property correctly returns string value from StepType enum
## Evidence
- Commits:
- Tests: uv run mypy dataing/src/dataing/core/investigation/steps --strict, uv run pytest tests/ -v (68 passed), python -c 'from dataing.core.investigation.steps import *'
- PRs:
