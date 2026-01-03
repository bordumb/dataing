# Architecture Overview

dataing uses a Hexagonal Architecture (Ports and Adapters) to maintain
a clean separation between business logic and infrastructure.

## Core Concepts

### Investigation Flow

1. **Context Gathering**: Discover database schema and optional lineage
2. **Hypothesis Generation**: Use LLM to generate potential root causes
3. **Parallel Investigation**: Execute queries to test each hypothesis
4. **Evidence Interpretation**: LLM interprets query results
5. **Synthesis**: Combine all evidence into a finding

### Event Sourcing

All investigation state is derived from an event stream:

```python
@dataclass
class InvestigationState:
    events: list[Event] = field(default_factory=list)

    def get_retry_count(self, hypothesis_id: str) -> int:
        # Derived from events, never stored as counter
        return sum(
            1 for e in self.events
            if e.type == "reflexion_attempted"
            and e.data.get("hypothesis_id") == hypothesis_id
        )
```

This ensures:

- Complete audit trail
- Impossible inconsistent state
- Easy debugging and replay

### Safety Layers

Safety is enforced at multiple levels:

1. **Query Validation**: sqlglot parses and validates all SQL
2. **Circuit Breaker**: Limits on queries, retries, and duration
3. **PII Detection**: Scans results for sensitive data
4. **Read-Only**: Only SELECT statements allowed

## Directory Structure

```
backend/src/dataing/
├── core/           # Pure domain logic (no dependencies)
│   ├── domain_types.py
│   ├── state.py
│   ├── interfaces.py
│   ├── orchestrator.py
│   └── exceptions.py
├── adapters/       # Infrastructure implementations
│   ├── db/         # Database adapters
│   ├── llm/        # LLM client
│   └── context/    # Context gathering
├── safety/         # Guardrails
│   ├── validator.py
│   ├── circuit_breaker.py
│   └── pii.py
├── prompts/        # YAML prompt templates
└── entrypoints/    # External interfaces
    ├── api/        # FastAPI
    └── mcp/        # MCP server
```

## Key Interfaces

The core defines Protocol classes that adapters implement:

```python
class DatabaseAdapter(Protocol):
    async def execute_query(self, sql: str) -> QueryResult: ...
    async def get_schema(self) -> SchemaContext: ...

class LLMClient(Protocol):
    async def generate_hypotheses(...) -> list[Hypothesis]: ...
    async def generate_query(...) -> str: ...
    async def interpret_evidence(...) -> Evidence: ...
    async def synthesize_findings(...) -> Finding: ...

class ContextEngine(Protocol):
    async def gather(self, alert: AnomalyAlert) -> InvestigationContext: ...
```

This allows:

- Easy testing with mock implementations
- Swapping adapters without changing core logic
- Clear boundaries between layers
