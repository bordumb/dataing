# fn-9.5 Refactor validate_query to use sqlglot

## Description

Replace the regex-based `validate_query` field validator on `QueryResponse.query` (lines 101-118) with the new sqlglot-based wrapper.

**File**: `dataing/src/dataing/agents/models.py`
**Lines**: 101-118

```python
# Before (regex-based):
@field_validator("query")
@classmethod
def validate_query(cls, v: str) -> str:
    # Strip markdown...
    # Check startswith SELECT...
    # Check LIMIT...
    return v.strip()

# After (sqlglot-based):
@field_validator("query")
@classmethod
def validate_query(cls, v: str) -> str:
    """Validate the generated SQL."""
    return _validate_sql_query(v, require_select=True)
```

Note: `require_select=True` because QueryResponse queries must be SELECT statements.

## Acceptance

- [ ] Validator uses `_validate_sql_query()` wrapper
- [ ] Markdown stripping still works
- [ ] LIMIT requirement still enforced
- [ ] Must be SELECT statement (enforced via sqlglot AST, not string check)
- [ ] Mutation statements blocked
- [ ] Existing behavior preserved for valid queries

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
