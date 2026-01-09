# Agents Refactor Design

## Summary

Extract LLM prompts into a dedicated prompt module and promote agents from an adapter to a first-class domain concept.

## Problem

Currently in `dataing/src/dataing/adapters/llm/client.py`:
- Agent initialization shows `instructions=""` which looks like a bug (though intentional)
- Actual prompts are buried in `_build_*` methods 400+ lines below
- Hard to understand what each agent does at a glance
- Agents are treated as an "adapter" when they're core to the investigation workflow

## Solution

### New Directory Structure

```
dataing/src/dataing/
├── agents/
│   ├── __init__.py           # Exports AgentClient, models
│   ├── client.py             # AgentClient facade (renamed from AnthropicClient)
│   ├── models.py             # Response models (renamed from response_models.py)
│   └── prompts/
│       ├── __init__.py       # Exports all prompts + protocol
│       ├── protocol.py       # PromptBuilder protocol/interface
│       ├── hypothesis.py     # Hypothesis generation prompts
│       ├── query.py          # Query generation prompts
│       ├── reflexion.py      # Query correction prompts
│       ├── interpretation.py # Evidence interpretation prompts
│       └── synthesis.py      # Finding synthesis prompts
├── adapters/
│   └── llm/                  # REMOVED
├── core/
│   └── ...                   # Unchanged
```

### Prompt Builder Protocol

Each prompt file implements a consistent interface:

```python
# agents/prompts/protocol.py
from typing import Protocol

class PromptBuilder(Protocol):
    """Interface for agent prompt builders."""

    SYSTEM_PROMPT: str  # Static system prompt template

    @staticmethod
    def build_system(**kwargs) -> str:
        """Build system prompt, optionally with dynamic values."""
        ...

    @staticmethod
    def build_user(**kwargs) -> str:
        """Build user prompt from context."""
        ...
```

Each prompt file exposes `SYSTEM_PROMPT`, `build_system()`, and `build_user()`:

```python
# agents/prompts/hypothesis.py
SYSTEM_PROMPT = """You are a data quality investigator...
...all the detailed instructions...
"""

def build_system(num_hypotheses: int = 5) -> str:
    """Build hypothesis system prompt."""
    return SYSTEM_PROMPT.format(num_hypotheses=num_hypotheses)

def build_user(alert: AnomalyAlert, context: InvestigationContext) -> str:
    """Build hypothesis user prompt."""
    # ... build from alert and context
```

### AgentClient Facade

The `client.py` becomes clean - just agent setup and delegation:

```python
# agents/client.py
from bond import BondAgent, StreamHandlers
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.output import PromptedOutput
from pydantic_ai.providers.anthropic import AnthropicProvider

from .models import HypothesesResponse, QueryResponse, ...
from .prompts import hypothesis, query, reflexion, interpretation, synthesis

class AgentClient:
    """LLM client facade for investigation agents.

    Uses BondAgent for type-safe, validated responses with streaming.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
    ) -> None:
        provider = AnthropicProvider(api_key=api_key)
        self._model = AnthropicModel(model, provider=provider)
        self._max_retries = max_retries

        # Agents initialized with empty instructions - prompts via dynamic_instructions
        self._hypothesis_agent = BondAgent(...)
        self._query_agent = BondAgent(...)
        self._interpretation_agent = BondAgent(...)
        self._synthesis_agent = BondAgent(...)

    async def generate_hypotheses(self, alert, context, num_hypotheses=5, handlers=None):
        system = hypothesis.build_system(num_hypotheses=num_hypotheses)
        user = hypothesis.build_user(alert=alert, context=context)

        result = await self._hypothesis_agent.ask(
            user, dynamic_instructions=system, handlers=handlers
        )
        return [Hypothesis(...) for h in result.hypotheses]
```

Each method is ~10 lines: build prompts, call agent, map response.

### Import Updates

**Orchestrator** (`core/orchestrator.py`):
```python
# Before
from dataing.adapters.llm.response_models import InterpretationResponse, SynthesisResponse

# After
from dataing.agents.models import InterpretationResponse, SynthesisResponse
```

**Dependency injection** (`entrypoints/api/deps.py`, `entrypoints/mcp/server.py`):
```python
# Before
from dataing.adapters.llm.client import AnthropicClient

# After
from dataing.agents import AgentClient
```

**Tests**:
```
# Move from tests/unit/adapters/llm/ → tests/unit/agents/
```

The `LLMClient` protocol in `core/interfaces.py` stays unchanged - `AgentClient` implements it.

## Tasks

1. Create `dataing/src/dataing/agents/` directory structure
2. Create `prompts/protocol.py` with `PromptBuilder` protocol
3. Extract prompts to individual files:
   - `hypothesis.py` (includes `_build_metric_context` helper)
   - `query.py`
   - `reflexion.py`
   - `interpretation.py`
   - `synthesis.py`
4. Move `response_models.py` → `agents/models.py`
5. Create `agents/client.py` with `AgentClient`
6. Create `agents/__init__.py` and `agents/prompts/__init__.py`
7. Update imports across codebase
8. Move tests from `tests/unit/adapters/llm/` → `tests/unit/agents/`
9. Remove `adapters/llm/` folder
10. Run tests to verify no breakage

## Benefits

1. **Readability**: Each agent's purpose and prompts are clear at a glance
2. **Maintainability**: Edit prompts in one place without scrolling through client code
3. **Testability**: Prompts can be unit tested independently
4. **Architecture**: Agents are core domain concepts, not infrastructure adapters
5. **Extensibility**: Easy to add new agent types or swap implementations
6. **Future-proof**: `AgentClient` name allows multi-model support

## Notes

- Pure refactor - no behavior changes
- The `bond/` package remains separate (generic agent runtime)
- `AgentClient` name is model-agnostic for future multi-model support
