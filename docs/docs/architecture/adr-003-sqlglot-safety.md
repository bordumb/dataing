# ADR-003: SQLGlot for Query Safety

## Status

Accepted

## Context

The system generates SQL queries using an LLM. We must ensure:

1. No mutation statements (DROP, DELETE, UPDATE, etc.)
2. Only SELECT statements are executed
3. All queries have LIMIT clauses
4. Protection against SQL injection patterns

## Decision

Use sqlglot for SQL parsing and validation:

```python
import sqlglot
from sqlglot import exp

def validate_query(sql: str) -> None:
    parsed = sqlglot.parse_one(sql, dialect="postgres")

    if not isinstance(parsed, exp.Select):
        raise QueryValidationError("Only SELECT allowed")

    if not parsed.find(exp.Limit):
        raise QueryValidationError("LIMIT required")
```

## Rationale

1. **Proper Parsing**: sqlglot produces an AST, not regex matching
2. **Dialect Support**: Works with Postgres, Trino, BigQuery, etc.
3. **Transformation**: Can add LIMIT if missing
4. **No False Negatives**: Unlike regex, catches all edge cases

## Consequences

### Positive

- Reliable detection of mutation statements
- Can transform queries (add LIMIT, etc.)
- Supports multiple SQL dialects
- Well-maintained open source library

### Negative

- Adds dependency (~5MB)
- Parsing adds small latency
- May reject valid but unusual SQL syntax

## Implementation

See `backend/src/dataing/safety/validator.py`:

- Parse with sqlglot
- Check statement type is SELECT
- Walk AST for forbidden nodes
- Require LIMIT clause
- Keyword check as secondary safety layer
