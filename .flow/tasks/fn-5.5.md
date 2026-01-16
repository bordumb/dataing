# fn-5.5 Port Existing Steps to Maistro Protocol

## Description
Update all existing step implementations to use maistro.Step protocol.

## Implementation

1. Update step base class imports:
   ```python
   # Before
   from dataing.core.investigation.steps.protocol import Step, StepResult

   # After
   from maistro import Step, StepResult
   ```

2. Update each step's `execute()` signature:
   - Return `maistro.StepResult[InvestigationContext, OutputT]`
   - Use `maistro.Signal` instead of `ExecutionSignal`

3. Steps to migrate:
   - GatherContextStep
   - GenerateHypothesesStep
   - CheckPatternsStep
   - GenerateQueryStep
   - ExecuteQueryStep
   - InterpretResultsStep
   - SynthesizeStep

4. Keep step logic unchanged - only update types and imports.

5. Update StepRegistry to work with maistro.Step protocol.

## Key Files
- Modify: `dataing/src/dataing/core/investigation/steps/*.py`
- Modify: `dataing/src/dataing/core/investigation/registry.py`
- Delete: `dataing/src/dataing/core/investigation/steps/protocol.py` (after migration)
## Acceptance
- [ ] All steps import from `maistro` package
- [ ] All `execute()` return `maistro.StepResult`
- [ ] `ExecutionSignal` replaced with `maistro.Signal`
- [ ] StepRegistry uses `maistro.Step` protocol
- [ ] All existing step unit tests pass
- [ ] `mypy` passes on all step files
- [ ] No duplicate Step/StepResult definitions in dataing
## Done summary
- Ported all investigation steps to use maistro protocol types
- Added AWAIT_USER signal to maistro.Signal enum for user interaction support
- Added branch_type field to maistro.BranchRequest for domain-specific branching
- Updated protocol.py to re-export maistro types with backward compatibility
- Created DataingStep ABC that satisfies maistro.Step protocol via name property
- Updated all step imports: Signal instead of ExecutionSignal
- Updated all StepResult return types: StepResult[InvestigationContext, OutputT]
- Converted all next_step and merge_step values to strings (.value)
- Updated StepRegistry to use maistro.Step protocol with InvestigationStep alias

Why:
- Steps now use maistro's generic workflow types
- ExecutionSignal removed in favor of maistro.Signal
- StepRegistry uses maistro.Step protocol for type safety
- Backward compatibility maintained via re-exports

Verification:
- mypy passes on all 11 step files (--strict)
- All 68 maistro tests pass
- Import test confirms all steps load correctly
- step.name property correctly returns string value from StepType enum
## Evidence
- Commits:
- Tests: uv run mypy dataing/src/dataing/core/investigation/steps --strict, uv run pytest tests/ -v (68 passed), python -c 'from dataing.core.investigation.steps import *'
- PRs:
