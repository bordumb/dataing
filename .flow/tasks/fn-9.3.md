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
- Added _strip_markdown() to handle markdown code blocks (```sql, unclosed, etc.)
- Added _validate_sql_query() wrapper that calls safety validator and translates exceptions
- Added require_select parameter to validate_query() in safety/validator.py
- Both functions are private (underscore prefix)
- All existing tests pass (38 validator tests)
- Lint and type checks pass
## Evidence
- Commits: 14c01768cc36594adf84434af8c9d1bfb89d3ede
- Tests: uv run pytest dataing/tests/unit/safety/test_validator.py -v
- PRs:
