# AnthropicClient BondAgent Refactor Design

**Date:** 2026-01-09
**Status:** Draft

## Overview

Refactor `AnthropicClient` to use `BondAgent` instead of raw `pydantic_ai.Agent`, adding streaming support via `StreamHandlers` parameter to all LLM methods.

## Goals

1. Replace raw `pydantic_ai.Agent` instances with `BondAgent` in `AnthropicClient`
2. Add `handlers: StreamHandlers | None` parameter to all public methods
3. Update `LLMClient` protocol to include streaming support
4. Thread handlers through `InvestigationOrchestrator` to enable UI streaming

## Files to Modify

| File | Changes |
|------|---------|
| `dataing/src/dataing/adapters/llm/client.py` | Replace `Agent` with `BondAgent`, add `handlers` param, change `.run()` to `.ask()` |
| `dataing/src/dataing/core/interfaces.py` | Add `handlers: StreamHandlers \| None = None` to all `LLMClient` methods |
| `dataing/src/dataing/core/orchestrator.py` | Accept `handlers` in `run_investigation`, thread through to LLM calls |

## Detailed Changes

### 1. client.py - AnthropicClient

**Imports:**
```python
# Remove
from pydantic_ai import Agent

# Add
from bond import BondAgent, StreamHandlers
```

**`__init__` method:**
```python
# Before
self._hypothesis_agent: Agent[None, HypothesesResponse] = Agent(
    model=self._model,
    output_type=PromptedOutput(HypothesesResponse),
    retries=max_retries,
)

# After
self._hypothesis_agent: BondAgent[HypothesesResponse, None] = BondAgent(
    name="hypothesis-generator",
    instructions="You are a data quality investigator.",
    model=self._model,
    output_type=PromptedOutput(HypothesesResponse),
    max_retries=max_retries,
)
```

**Method signatures (all 4 methods):**
```python
# Before
async def generate_hypotheses(
    self,
    alert: AnomalyAlert,
    context: InvestigationContext,
    num_hypotheses: int = 5,
) -> list[Hypothesis]:

# After
async def generate_hypotheses(
    self,
    alert: AnomalyAlert,
    context: InvestigationContext,
    num_hypotheses: int = 5,
    handlers: StreamHandlers | None = None,
) -> list[Hypothesis]:
```

**Method internals:**
```python
# Before
result = await self._hypothesis_agent.run(
    user_prompt,
    instructions=system_prompt,
)
return [Hypothesis(...) for h in result.output.hypotheses]

# After
result = await self._hypothesis_agent.ask(
    user_prompt,
    dynamic_instructions=system_prompt,
    handlers=handlers,
)
return [Hypothesis(...) for h in result.hypotheses]  # .output removed
```

### 2. interfaces.py - LLMClient Protocol

Add import and update all method signatures:

```python
from bond import StreamHandlers

@runtime_checkable
class LLMClient(Protocol):
    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
        handlers: StreamHandlers | None = None,
    ) -> list[Hypothesis]:
        ...

    async def generate_query(
        self,
        hypothesis: Hypothesis,
        schema: SchemaResponse,
        previous_error: str | None = None,
        handlers: StreamHandlers | None = None,
    ) -> str:
        ...

    async def interpret_evidence(
        self,
        hypothesis: Hypothesis,
        query: str,
        results: QueryResult,
        handlers: StreamHandlers | None = None,
    ) -> Evidence:
        ...

    async def synthesize_findings(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
        handlers: StreamHandlers | None = None,
    ) -> Finding:
        ...
```

### 3. orchestrator.py - InvestigationOrchestrator

**Import:**
```python
from bond import StreamHandlers
```

**`run_investigation`:**
```python
async def run_investigation(
    self,
    state: InvestigationState,
    data_adapter: SQLAdapter | None = None,
    handlers: StreamHandlers | None = None,  # NEW
) -> Finding:
```

**Internal method calls - thread handlers through:**
- `_generate_hypotheses(state, handlers)`
- `_investigate_parallel(state, hypotheses, handlers)`
- `_investigate_hypothesis(state, hypothesis, handlers)`
- `_synthesize(state, evidence, start_time, handlers)`

**Each internal method passes handlers to LLM calls:**
```python
hypotheses = await self.llm.generate_hypotheses(
    alert=state.alert,
    context=context,
    num_hypotheses=self.config.max_hypotheses,
    handlers=handlers,
)
```

## Key Transformation Patterns

| Before | After |
|--------|-------|
| `Agent[None, T]` | `BondAgent[T, None]` |
| `Agent(model=..., output_type=..., retries=...)` | `BondAgent(name=..., instructions=..., model=..., output_type=..., max_retries=...)` |
| `agent.run(prompt, instructions=...)` | `agent.ask(prompt, dynamic_instructions=..., handlers=...)` |
| `result.output.field` | `result.field` |

## Notes

- No pyproject.toml changes needed - monorepo already configured
- Prompt building methods unchanged - they become `dynamic_instructions`
- Response models unchanged
- All changes are additive with optional `handlers` parameter
