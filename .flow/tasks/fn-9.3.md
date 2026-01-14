# fn-9.3 Create validation wrapper with markdown stripping

## Description

Create a utility function in `dataing/src/dataing/agents/models.py` that:
1. Strips markdown code blocks from LLM-generated SQL
2. Calls the existing `validate_query()` from `safety/validator.py`
3. Catches `QueryValidationError` and re-raises as `ValueError` (required for Pydantic)
4. Returns the stripped query string

**File**: `dataing/src/dataing/agents/models.py`

```python
from dataing.core.exceptions import QueryValidationError
from dataing.safety.validator import validate_query as validate_query_safety

def _strip_markdown(query: str) -> str:
    """Strip markdown code blocks from query."""
    if query.startswith("```"):
        lines = query.strip().split("\n")
        # Handle both closed and unclosed blocks
        if lines[-1] == "```":
            return "\n".join(lines[1:-1])
        return "\n".join(lines[1:])
    return query

def _validate_sql_query(
    query: str,
    *,
    require_select: bool = False,
    dialect: str = "postgres",
) -> str:
    """Validate SQL query using sqlglot. Returns stripped query."""
    stripped = _strip_markdown(query).strip()
    if not stripped:
        raise ValueError("Empty query after stripping markdown")

    try:
        validate_query_safety(stripped, dialect=dialect, require_select=require_select)
    except QueryValidationError as e:
        raise ValueError(str(e)) from None

    return stripped
```

## Acceptance

- [ ] `_strip_markdown()` function handles: ```sql, ```SQL, ```postgresql, unclosed blocks
- [ ] `_validate_sql_query()` calls safety validator and translates exceptions
- [ ] Empty query after strip raises ValueError
- [ ] Both functions are private (underscore prefix)
- [ ] No code duplication with safety/validator.py

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
