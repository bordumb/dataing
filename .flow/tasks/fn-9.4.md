# fn-9.4 Refactor validate_query_safety to use sqlglot

## Description

Replace the regex-based `validate_query_safety` field validator on `HypothesisResponse.suggested_query` (lines 45-79) with the new sqlglot-based wrapper.

**File**: `dataing/src/dataing/agents/models.py`
**Lines**: 45-79

```python
# Before (regex-based):
@field_validator("suggested_query")
@classmethod
def validate_query_safety(cls, v: str) -> str:
    # Strip markdown...
    # Regex check for dangerous keywords...
    return v.strip()

# After (sqlglot-based):
@field_validator("suggested_query")
@classmethod
def validate_query_safety(cls, v: str) -> str:
    """Validate query safety: strip markdown, require LIMIT, block mutations."""
    return _validate_sql_query(v, require_select=False)
```

Note: `require_select=False` because hypothesis queries don't strictly require SELECT (could be EXPLAIN, etc.).

## Acceptance

- [ ] Validator uses `_validate_sql_query()` wrapper
- [ ] Markdown stripping still works
- [ ] LIMIT requirement still enforced
- [ ] Mutation statements (INSERT, UPDATE, DELETE, DROP, MERGE, etc.) blocked
- [ ] No false positives for column names like `deleted_at`, `update_log`
- [ ] Existing behavior preserved for valid queries

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
