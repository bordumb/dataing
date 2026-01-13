# fn-4.3 RecursiveAnalysisStep with Code-Observe-Loop

## Description

Create a new step that implements the Code-Observe-Loop pattern, allowing the LLM to iteratively explore data via code execution.

### RecursiveAnalysisStep

Create `backend/src/dataing/core/investigation/steps/recursive_analyze.py`:

```python
class RecursiveAnalysisStep(Step):
    step_type = StepType.RECURSIVE_ANALYZE

    async def execute(
        self,
        context: InvestigationContext,
        input_data: dict[str, Any] | None = None,
    ) -> StepResult:
        """Execute Code-Observe-Loop until termination or max iterations."""
```

### Loop Flow

```
1. Build prompt with data references + prior observations
2. LLM generates: THOUGHT (reasoning) + ACTION (code or STOP_AND_REPORT)
3. If ACTION is code:
   a. Execute in AnalysisSandbox
   b. Add observation to history
   c. Increment iteration counter
   d. If iteration < max_iterations: goto 1
4. If ACTION is STOP_AND_REPORT or max iterations reached:
   a. Build final summary
   b. Return StepResult with findings
```

### Configuration

```python
@dataclass
class RecursiveAnalysisConfig:
    max_iterations: int = 10
    max_code_retries: int = 3  # Retries on syntax/runtime errors
    timeout_seconds: int = 60  # Total step timeout
```

### Observation Storage

Store observations in step-local state (not in frozen context):

```python
@dataclass
class CodeObservation:
    iteration: int
    thought: str
    code: str
    result: ExecutionResult
    timestamp: datetime
```

### StepType Addition

Add to `backend/src/dataing/core/investigation/values.py`:

```python
class StepType(StrEnum):
    # Existing...
    RECURSIVE_ANALYZE = "recursive_analyze"
```

### Files to Create/Modify

- `backend/src/dataing/core/investigation/steps/recursive_analyze.py` (new)
- `backend/src/dataing/core/investigation/values.py` (add StepType)
- `backend/src/dataing/adapters/investigation/step_factory.py` (register step)
- `backend/tests/unit/core/investigation/steps/test_recursive_analyze.py` (new)

### References

- Step Protocol: `core/investigation/steps/protocol.py:60-93`
- Existing step example: `core/investigation/steps/synthesize.py:45-130`
## Acceptance
- [ ] `RecursiveAnalysisStep` class implements Step protocol
- [ ] `StepType.RECURSIVE_ANALYZE` added to enum
- [ ] Code-Observe-Loop executes up to max_iterations (default 10)
- [ ] LLM can terminate early with STOP_AND_REPORT token
- [ ] Syntax/runtime errors trigger retry (up to 3 retries)
- [ ] Observations stored with thought, code, result, timestamp
- [ ] Step registered in step factory
- [ ] Unit tests: happy path loop, early termination, error retry, max iterations
- [ ] mypy --strict passes
- [ ] ruff check passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
