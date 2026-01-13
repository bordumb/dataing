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
TBD

## Evidence
- Commits:
- Tests:
- PRs:
