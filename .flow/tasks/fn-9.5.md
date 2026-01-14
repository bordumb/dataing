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
- Replaced string-based validate_query with _validate_sql_query wrapper
- Uses sqlglot AST for SELECT requirement (not string prefix check)
- Consistent validation with HypothesisResponse
- All 52 tests pass
- Lint and type checks pass
## Evidence
- Commits: 24d1d77662843c2efb49a72fa44ac1cd28af8978
- Tests: uv run pytest dataing/tests/unit/agents/test_models.py dataing/tests/unit/safety/test_validator.py -v
- PRs:
