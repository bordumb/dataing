# fn-4.8 Structured audit logging for reasoning traces

## Description


Implement structured audit logging to capture the LLM's reasoning process (Thought → Action → Observation).

### Reasoning Trace Schema

Create `backend/src/dataing/adapters/audit/trace.py`:

```python
@dataclass(frozen=True)
class ReasoningStep:
    step_index: int
    thought: str  # LLM's reasoning before action
    action_type: Literal["code", "branch", "stop"]
    action_content: str  # Code string or branch rationale
    observation: str | None  # Execution result (None if stop)
    error: str | None  # Error message if action failed
    timestamp: datetime
    duration_ms: int

@dataclass(frozen=True)
class ReasoningTrace:
    investigation_id: UUID
    step_type: StepType
    steps: tuple[ReasoningStep, ...]
    total_tokens: int
    total_duration_ms: int
    created_at: datetime
```

### Trace Collector

```python
class TraceCollector:
    """Collects reasoning steps during RecursiveAnalysisStep execution."""

    def __init__(self, investigation_id: UUID):
        self._investigation_id = investigation_id
        self._steps: list[ReasoningStep] = []

    def record_step(
        self,
        thought: str,
        action_type: str,
        action_content: str,
        observation: str | None,
        error: str | None,
        duration_ms: int,
    ) -> None:
        """Record a single reasoning step."""

    def finalize(self) -> ReasoningTrace:
        """Build immutable trace from collected steps."""
```

### Storage

Extend `AuditRepository` at `adapters/audit/__init__.py`:

```python
class AuditRepository(Protocol):
    async def save_trace(self, trace: ReasoningTrace) -> None:
        """Persist reasoning trace."""

    async def get_traces(
        self,
        investigation_id: UUID,
        step_type: StepType | None = None,
    ) -> list[ReasoningTrace]:
        """Retrieve traces for an investigation."""
```

### Integration Points

1. `RecursiveAnalysisStep` creates `TraceCollector` at start
2. Each Code-Observe iteration calls `collector.record_step()`
3. On step completion, call `audit_repo.save_trace(collector.finalize())`

### Files to Create/Modify

- `backend/src/dataing/adapters/audit/trace.py` (new)
- `backend/src/dataing/adapters/audit/__init__.py` (extend repository)
- `backend/src/dataing/core/investigation/steps/recursive_analyze.py` (integrate collector)
- `backend/tests/unit/adapters/audit/test_trace.py` (new)

### References

- Audit stub: `adapters/audit/__init__.py:13-70`
- RecursiveAnalysisStep: created in fn-4.3
## Acceptance
- [ ] `ReasoningStep` dataclass with thought, action_type, action_content, observation, error, timestamp
- [ ] `ReasoningTrace` dataclass aggregating steps with metadata
- [ ] `TraceCollector` class for collecting steps during execution
- [ ] `AuditRepository.save_trace()` method implemented
- [ ] `AuditRepository.get_traces()` method for retrieval
- [ ] `RecursiveAnalysisStep` integrates TraceCollector
- [ ] Each Code-Observe cycle recorded in trace
- [ ] Traces include error details when actions fail
- [ ] Unit test: trace collection during happy path
- [ ] Unit test: trace includes errors on failure
- [ ] Unit test: save and retrieve trace
- [ ] mypy --strict passes
- [ ] ruff check passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
