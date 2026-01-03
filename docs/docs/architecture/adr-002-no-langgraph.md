# ADR-002: No LangGraph

## Status

Accepted

## Context

We need to orchestrate an agentic workflow that:

- Generates hypotheses in parallel
- Executes queries to test hypotheses
- Retries on failure with reflexion
- Synthesizes findings

LangGraph is a popular framework for building such workflows.

## Decision

Use pure Python asyncio instead of LangGraph or similar frameworks.

## Rationale

1. **Simplicity**: asyncio.gather is sufficient for our needs
2. **Transparency**: No hidden state machine complexity
3. **Debuggability**: Standard Python debugging tools work
4. **Performance**: No framework overhead
5. **Maintainability**: Fewer dependencies to update

Our workflow is simple enough:

```python
# This is all we need for parallel execution
results = await asyncio.gather(
    *[investigate_hypothesis(h) for h in hypotheses],
    return_exceptions=True
)
```

## Consequences

### Positive

- ~100 lines of orchestration code vs thousands with LangGraph
- No framework learning curve
- Easy to understand and modify

### Negative

- No built-in visualization of workflow state
- Must implement our own event sourcing (which we wanted anyway)
- No pre-built tools/agents from LangGraph ecosystem

## Implementation

- Use `asyncio.gather` for parallel hypothesis investigation
- Implement event sourcing manually in `state.py`
- Use structured logging for observability
