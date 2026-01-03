# ADR-004: Event Sourcing for State

## Status

Accepted

## Context

Investigation state includes:

- Retry counts per hypothesis
- Query execution history
- Current status
- Consecutive failure counts

We must prevent infinite loops and track all actions.

## Decision

Use event sourcing: all state is derived from an append-only event log.

```python
@dataclass
class InvestigationState:
    events: list[Event] = field(default_factory=list)

    def get_retry_count(self, hypothesis_id: str) -> int:
        """DERIVED from events, not stored."""
        return sum(
            1 for e in self.events
            if e.type == "reflexion_attempted"
            and e.data.get("hypothesis_id") == hypothesis_id
        )
```

## Rationale

1. **Prevents Infinite Loops**: Retry count cannot be accidentally reset
2. **Complete Audit Trail**: Every action is recorded
3. **Debuggability**: Can replay exact sequence of events
4. **Consistency**: Single source of truth (events)

### Why Not Mutable Counters?

With mutable counters:

```python
# BUG: Counter could be reset accidentally
state.retry_count = 0
```

With event sourcing:

```python
# Retry count is computed, cannot be directly modified
count = state.get_retry_count(hypothesis_id)  # Always correct
```

## Consequences

### Positive

- Impossible to have inconsistent state
- Natural audit log
- Easy to add new derived values
- Testable state transitions

### Negative

- Slightly more complex API
- Events list grows during investigation
- Computed properties have O(n) complexity

## Implementation

See `backend/src/dataing/core/state.py`:

- `Event` is a frozen dataclass
- `InvestigationState` stores events list
- All counts are computed via properties
- `append_event()` returns new state (immutable update)
