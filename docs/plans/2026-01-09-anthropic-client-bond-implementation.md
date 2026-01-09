# AnthropicClient BondAgent Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor AnthropicClient to use BondAgent instead of raw pydantic_ai.Agent, adding streaming support via StreamHandlers.

**Architecture:** Replace raw Agent instances with BondAgent, add optional `handlers` parameter to all LLM methods, thread handlers through the orchestrator pipeline.

**Tech Stack:** Python 3.11+, PydanticAI, bond (BondAgent), pytest

---

## Task 1: Update LLMClient Protocol

**Files:**
- Modify: `dataing/src/dataing/core/interfaces.py:76-169`
- Test: Existing tests should still pass

**Step 1: Add StreamHandlers import**

Add to the TYPE_CHECKING block in `interfaces.py`:

```python
if TYPE_CHECKING:
    from bond import StreamHandlers
    from dataing.adapters.datasource.base import BaseAdapter
    # ... rest of imports
```

**Step 2: Update generate_hypotheses signature**

Change lines 89-108:

```python
async def generate_hypotheses(
    self,
    alert: AnomalyAlert,
    context: InvestigationContext,
    num_hypotheses: int = 5,
    handlers: StreamHandlers | None = None,
) -> list[Hypothesis]:
    """Generate hypotheses for an anomaly.

    Args:
        alert: The anomaly alert to investigate.
        context: Available schema and lineage context.
        num_hypotheses: Target number of hypotheses to generate.
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        List of generated hypotheses.

    Raises:
        LLMError: If LLM call fails.
    """
    ...
```

**Step 3: Update generate_query signature**

Change lines 110-129:

```python
async def generate_query(
    self,
    hypothesis: Hypothesis,
    schema: SchemaResponse,
    previous_error: str | None = None,
    handlers: StreamHandlers | None = None,
) -> str:
    """Generate SQL query to test a hypothesis.

    Args:
        hypothesis: The hypothesis to test.
        schema: Available database schema.
        previous_error: Error from previous query attempt (for reflexion).
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        SQL query string.

    Raises:
        LLMError: If LLM call fails.
    """
    ...
```

**Step 4: Update interpret_evidence signature**

Change lines 131-150:

```python
async def interpret_evidence(
    self,
    hypothesis: Hypothesis,
    query: str,
    results: QueryResult,
    handlers: StreamHandlers | None = None,
) -> Evidence:
    """Interpret query results as evidence.

    Args:
        hypothesis: The hypothesis being tested.
        query: The query that was executed.
        results: The query results to interpret.
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        Evidence with interpretation and confidence.

    Raises:
        LLMError: If LLM call fails.
    """
    ...
```

**Step 5: Update synthesize_findings signature**

Change lines 152-169:

```python
async def synthesize_findings(
    self,
    alert: AnomalyAlert,
    evidence: list[Evidence],
    handlers: StreamHandlers | None = None,
) -> Finding:
    """Synthesize all evidence into a root cause finding.

    Args:
        alert: The original anomaly alert.
        evidence: All collected evidence.
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        Finding with root cause and recommendations.

    Raises:
        LLMError: If LLM call fails.
    """
    ...
```

**Step 6: Run tests to verify protocol changes don't break anything**

Run: `uv run pytest dataing/tests/unit/core/ -v --tb=short -x`
Expected: Tests pass (pre-existing fixture errors are OK)

**Step 7: Commit**

```bash
git add dataing/src/dataing/core/interfaces.py
git commit -m "feat(interfaces): add StreamHandlers to LLMClient protocol"
```

---

## Task 2: Refactor AnthropicClient Imports and Init

**Files:**
- Modify: `dataing/src/dataing/adapters/llm/client.py:1-78`

**Step 1: Update imports**

Replace lines 1-30:

```python
"""Anthropic Claude implementation with BondAgent structured outputs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from bond import BondAgent, StreamHandlers
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.output import PromptedOutput

from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    InvestigationContext,
)
from dataing.core.exceptions import LLMError

from .response_models import (
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import QueryResult, SchemaResponse
```

**Step 2: Update __init__ with BondAgent instances**

Replace lines 32-78:

```python
class AnthropicClient:
    """Anthropic Claude implementation with streaming support.

    Uses BondAgent for type-safe, validated LLM responses with optional streaming.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
    ) -> None:
        """Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model to use.
            max_retries: Max retries on validation failure.
        """
        os.environ["ANTHROPIC_API_KEY"] = api_key
        self._model = AnthropicModel(model)

        self._hypothesis_agent: BondAgent[HypothesesResponse, None] = BondAgent(
            name="hypothesis-generator",
            instructions="You are a data quality investigator.",
            model=self._model,
            output_type=PromptedOutput(HypothesesResponse),
            max_retries=max_retries,
        )
        self._interpretation_agent: BondAgent[InterpretationResponse, None] = BondAgent(
            name="evidence-interpreter",
            instructions="You analyze query results for evidence.",
            model=self._model,
            output_type=PromptedOutput(InterpretationResponse),
            max_retries=max_retries,
        )
        self._synthesis_agent: BondAgent[SynthesisResponse, None] = BondAgent(
            name="finding-synthesizer",
            instructions="You synthesize investigation findings.",
            model=self._model,
            output_type=PromptedOutput(SynthesisResponse),
            max_retries=max_retries,
        )
        self._query_agent: BondAgent[QueryResponse, None] = BondAgent(
            name="sql-generator",
            instructions="You are a SQL expert.",
            model=self._model,
            output_type=PromptedOutput(QueryResponse),
            max_retries=max_retries,
        )
```

**Step 3: Run import check**

Run: `uv run python -c "from dataing.adapters.llm.client import AnthropicClient; print('OK')"`
Expected: OK (no import errors)

**Step 4: Commit**

```bash
git add dataing/src/dataing/adapters/llm/client.py
git commit -m "refactor(llm): replace Agent with BondAgent in AnthropicClient init"
```

---

## Task 3: Refactor generate_hypotheses Method

**Files:**
- Modify: `dataing/src/dataing/adapters/llm/client.py:79-123`

**Step 1: Update generate_hypotheses signature and implementation**

Replace the method:

```python
async def generate_hypotheses(
    self,
    alert: AnomalyAlert,
    context: InvestigationContext,
    num_hypotheses: int = 5,
    handlers: StreamHandlers | None = None,
) -> list[Hypothesis]:
    """Generate hypotheses for an anomaly.

    Args:
        alert: The anomaly alert to investigate.
        context: Available schema and lineage context.
        num_hypotheses: Target number of hypotheses.
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        List of validated Hypothesis objects.

    Raises:
        LLMError: If LLM call fails after retries.
    """
    system_prompt = self._build_hypothesis_system_prompt(num_hypotheses)
    user_prompt = self._build_hypothesis_user_prompt(alert, context)

    try:
        result = await self._hypothesis_agent.ask(
            user_prompt,
            dynamic_instructions=system_prompt,
            handlers=handlers,
        )

        return [
            Hypothesis(
                id=h.id,
                title=h.title,
                category=h.category,
                reasoning=h.reasoning,
                suggested_query=h.suggested_query,
            )
            for h in result.hypotheses
        ]

    except Exception as e:
        raise LLMError(
            f"Hypothesis generation failed: {e}",
            retryable=False,
        ) from e
```

**Step 2: Run tests**

Run: `uv run pytest dataing/tests/unit/adapters/llm/test_client.py -v --tb=short -x`
Expected: Tests pass

**Step 3: Commit**

```bash
git add dataing/src/dataing/adapters/llm/client.py
git commit -m "refactor(llm): migrate generate_hypotheses to BondAgent.ask"
```

---

## Task 4: Refactor generate_query Method

**Files:**
- Modify: `dataing/src/dataing/adapters/llm/client.py:124-163`

**Step 1: Update generate_query signature and implementation**

Replace the method:

```python
async def generate_query(
    self,
    hypothesis: Hypothesis,
    schema: SchemaResponse,
    previous_error: str | None = None,
    handlers: StreamHandlers | None = None,
) -> str:
    """Generate SQL query to test a hypothesis.

    Args:
        hypothesis: The hypothesis to test.
        schema: Available database schema.
        previous_error: Error from previous attempt (for reflexion).
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        Validated SQL query string.

    Raises:
        LLMError: If query generation fails.
    """
    if previous_error:
        prompt = self._build_reflexion_prompt(hypothesis, previous_error)
        system = self._build_reflexion_system_prompt(schema)
    else:
        prompt = self._build_query_prompt(hypothesis)
        system = self._build_query_system_prompt(schema)

    try:
        result = await self._query_agent.ask(
            prompt,
            dynamic_instructions=system,
            handlers=handlers,
        )
        return result.query

    except Exception as e:
        raise LLMError(
            f"Query generation failed: {e}",
            retryable=True,
        ) from e
```

**Step 2: Run tests**

Run: `uv run pytest dataing/tests/unit/adapters/llm/test_client.py -v --tb=short -x`
Expected: Tests pass

**Step 3: Commit**

```bash
git add dataing/src/dataing/adapters/llm/client.py
git commit -m "refactor(llm): migrate generate_query to BondAgent.ask"
```

---

## Task 5: Refactor interpret_evidence Method

**Files:**
- Modify: `dataing/src/dataing/adapters/llm/client.py:164-210`

**Step 1: Update interpret_evidence signature and implementation**

Replace the method:

```python
async def interpret_evidence(
    self,
    hypothesis: Hypothesis,
    query: str,
    results: QueryResult,
    handlers: StreamHandlers | None = None,
) -> Evidence:
    """Interpret query results as evidence.

    Args:
        hypothesis: The hypothesis being tested.
        query: The query that was executed.
        results: The query results.
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        Evidence with validated interpretation.
    """
    prompt = self._build_interpretation_prompt(hypothesis, query, results)
    system = self._build_interpretation_system_prompt()

    try:
        result = await self._interpretation_agent.ask(
            prompt,
            dynamic_instructions=system,
            handlers=handlers,
        )

        return Evidence(
            hypothesis_id=hypothesis.id,
            query=query,
            result_summary=results.to_summary(),
            row_count=results.row_count,
            supports_hypothesis=result.supports_hypothesis,
            confidence=result.confidence,
            interpretation=result.interpretation,
        )

    except Exception as e:
        return Evidence(
            hypothesis_id=hypothesis.id,
            query=query,
            result_summary=results.to_summary(),
            row_count=results.row_count,
            supports_hypothesis=None,
            confidence=0.3,
            interpretation=f"Interpretation failed: {e}",
        )
```

**Step 2: Run tests**

Run: `uv run pytest dataing/tests/unit/adapters/llm/test_client.py -v --tb=short -x`
Expected: Tests pass

**Step 3: Commit**

```bash
git add dataing/src/dataing/adapters/llm/client.py
git commit -m "refactor(llm): migrate interpret_evidence to BondAgent.ask"
```

---

## Task 6: Refactor synthesize_findings Method

**Files:**
- Modify: `dataing/src/dataing/adapters/llm/client.py:211-252`

**Step 1: Update synthesize_findings signature and implementation**

Replace the method:

```python
async def synthesize_findings(
    self,
    alert: AnomalyAlert,
    evidence: list[Evidence],
    handlers: StreamHandlers | None = None,
) -> Finding:
    """Synthesize all evidence into a root cause finding.

    Args:
        alert: The original anomaly alert.
        evidence: All collected evidence.
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        Finding with validated root cause and recommendations.

    Raises:
        LLMError: If synthesis fails.
    """
    prompt = self._build_synthesis_prompt(alert, evidence)
    system = self._build_synthesis_system_prompt()

    try:
        result = await self._synthesis_agent.ask(
            prompt,
            dynamic_instructions=system,
            handlers=handlers,
        )

        return Finding(
            investigation_id="",
            status="completed" if result.root_cause else "inconclusive",
            root_cause=result.root_cause,
            confidence=result.confidence,
            evidence=evidence,
            recommendations=result.recommendations,
            duration_seconds=0.0,
        )

    except Exception as e:
        raise LLMError(
            f"Synthesis failed: {e}",
            retryable=False,
        ) from e
```

**Step 2: Run all LLM tests**

Run: `uv run pytest dataing/tests/unit/adapters/llm/ -v --tb=short`
Expected: All 14 tests pass

**Step 3: Commit**

```bash
git add dataing/src/dataing/adapters/llm/client.py
git commit -m "refactor(llm): migrate synthesize_findings to BondAgent.ask"
```

---

## Task 7: Update Orchestrator to Thread Handlers

**Files:**
- Modify: `dataing/src/dataing/core/orchestrator.py`

**Step 1: Add StreamHandlers import**

Add to imports at line 30:

```python
from bond import StreamHandlers
```

**Step 2: Update run_investigation signature**

Change the method signature (around line 111):

```python
async def run_investigation(
    self,
    state: InvestigationState,
    data_adapter: SQLAdapter | None = None,
    handlers: StreamHandlers | None = None,
) -> Finding:
    """Execute a complete investigation.

    Args:
        state: Initial investigation state with alert.
        data_adapter: Optional adapter for tenant's data source.
        handlers: Optional streaming handlers for real-time updates.

    Returns:
        Finding with root cause and recommendations.
    """
```

**Step 3: Update internal method calls to pass handlers**

In `run_investigation`, update the calls (around lines 181-189):

```python
# 2. Generate Hypotheses
state, hypotheses = await self._generate_hypotheses(state, handlers)
log.info("Hypotheses generated", count=len(hypotheses))

# 3. Investigate Hypotheses (Parallel Fan-Out)
evidence = await self._investigate_parallel(state, hypotheses, handlers)
log.info("Investigation complete", evidence_count=len(evidence))

# 4. Synthesize Findings (Fan-In)
finding = await self._synthesize(state, evidence, start_time, handlers)
```

**Step 4: Update _generate_hypotheses signature and call**

```python
async def _generate_hypotheses(
    self,
    state: InvestigationState,
    handlers: StreamHandlers | None = None,
) -> tuple[InvestigationState, list[Hypothesis]]:
    """Generate hypotheses using LLM."""
    assert state.schema_context is not None
    context = InvestigationContext(
        schema=state.schema_context,
        lineage=state.lineage_context,
    )

    hypotheses = await self.llm.generate_hypotheses(
        alert=state.alert,
        context=context,
        num_hypotheses=self.config.max_hypotheses,
        handlers=handlers,
    )
    # ... rest unchanged
```

**Step 5: Update _investigate_parallel signature and call**

```python
async def _investigate_parallel(
    self,
    state: InvestigationState,
    hypotheses: list[Hypothesis],
    handlers: StreamHandlers | None = None,
) -> list[Evidence]:
    """Fan-out: Investigate all hypotheses in parallel."""
    tasks = [self._investigate_hypothesis(state, h, handlers) for h in hypotheses]
    # ... rest unchanged
```

**Step 6: Update _investigate_hypothesis signature and calls**

```python
async def _investigate_hypothesis(
    self,
    state: InvestigationState,
    hypothesis: Hypothesis,
    handlers: StreamHandlers | None = None,
) -> list[Evidence]:
    """Investigate a single hypothesis with retry/reflexion loop."""
    # ... inside the method, update the LLM calls:

    query = await self.llm.generate_query(
        hypothesis=hypothesis,
        schema=state.schema_context,
        previous_error=previous_error,
        handlers=handlers,
    )

    # ... and later:

    ev = await self.llm.interpret_evidence(hypothesis, query, result, handlers)
```

**Step 7: Update _synthesize signature and call**

```python
async def _synthesize(
    self,
    state: InvestigationState,
    evidence: list[Evidence],
    start_time: float,
    handlers: StreamHandlers | None = None,
) -> Finding:
    """Fan-in: Synthesize all evidence into a finding."""
    finding = await self.llm.synthesize_findings(
        alert=state.alert,
        evidence=evidence,
        handlers=handlers,
    )
    # ... rest unchanged
```

**Step 8: Run orchestrator tests**

Run: `uv run pytest dataing/tests/unit/core/test_orchestrator.py -v --tb=short`
Expected: Tests pass

**Step 9: Commit**

```bash
git add dataing/src/dataing/core/orchestrator.py
git commit -m "feat(orchestrator): thread StreamHandlers through investigation pipeline"
```

---

## Task 8: Update llm/__init__.py Exports

**Files:**
- Modify: `dataing/src/dataing/adapters/llm/__init__.py`

**Step 1: Check current exports and add StreamHandlers**

Read the file first, then update to re-export StreamHandlers:

```python
"""LLM adapters for investigation."""

from bond import StreamHandlers

from .client import AnthropicClient
from .response_models import (
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)

__all__ = [
    "AnthropicClient",
    "StreamHandlers",
    "HypothesesResponse",
    "InterpretationResponse",
    "QueryResponse",
    "SynthesisResponse",
]
```

**Step 2: Run full test suite**

Run: `uv run pytest dataing/tests/unit/adapters/llm/ dataing/tests/unit/core/test_orchestrator.py -v --tb=short`
Expected: All tests pass

**Step 3: Commit**

```bash
git add dataing/src/dataing/adapters/llm/__init__.py
git commit -m "feat(llm): export StreamHandlers from adapters.llm"
```

---

## Task 9: Run Full Test Suite and Type Check

**Step 1: Run all unit tests**

Run: `uv run pytest dataing/tests/unit/ -v --tb=short`
Expected: Tests pass (pre-existing fixture errors OK)

**Step 2: Run type checker**

Run: `uv run mypy dataing/src/dataing/adapters/llm/client.py dataing/src/dataing/core/interfaces.py dataing/src/dataing/core/orchestrator.py --strict`
Expected: No new errors

**Step 3: Run linter**

Run: `uv run ruff check dataing/src/dataing/adapters/llm/ dataing/src/dataing/core/`
Expected: No errors

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address type and lint issues from refactor"
```

---

## Summary

After completing all tasks, you will have:

1. `LLMClient` protocol with `handlers` parameter on all methods
2. `AnthropicClient` using `BondAgent` instead of raw `Agent`
3. `InvestigationOrchestrator` threading handlers through the pipeline
4. Full streaming support for real-time UI updates
5. All existing tests passing
