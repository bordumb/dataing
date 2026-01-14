# Replace Regex SQL Validation with sqlglot

## Overview

Replace the regex-based SQL validation in `dataing/src/dataing/agents/models.py` with robust sqlglot-based parsing. The codebase already has a sqlglot validator at `dataing/src/dataing/safety/validator.py` - this epic refactors the Pydantic field validators to leverage it.

## Scope

**In scope:**
- Refactor `validate_query_safety` validator on `HypothesisResponse.suggested_query` (lines 45-79)
- Refactor `validate_query` validator on `QueryResponse.query` (lines 101-118)
- Add `exp.Merge` to FORBIDDEN_STATEMENTS in safety/validator.py
- Handle multi-statement queries (detect and reject)
- Keep markdown stripping logic
- Add comprehensive tests

**Out of scope:**
- Changing the safety/validator.py interface significantly
- Adding dialect inference based on datasource
- Query normalization/reformatting via sqlglot

## Approach

1. **Add MERGE to safety validator** - The existing regex validator blocks MERGE but sqlglot's FORBIDDEN_STATEMENTS is missing it

2. **Create wrapper function** - Add a utility function that:
   - Strips markdown code blocks
   - Calls the existing `validate_query()` from safety/validator.py
   - Catches `QueryValidationError` and re-raises as `ValueError` (required for Pydantic)
   - Returns the stripped query string

3. **Refactor validators** - Update both field validators to use the wrapper

4. **Handle multi-statement** - Use `sqlglot.parse()` to detect multi-statement queries

5. **Add tests** - Cover all edge cases identified in gap analysis

## Key Files

| File | Changes |
|------|---------|
| `dataing/src/dataing/safety/validator.py:37` | Add `exp.Merge` to FORBIDDEN_STATEMENTS |
| `dataing/src/dataing/agents/models.py:45-79` | Refactor `validate_query_safety` |
| `dataing/src/dataing/agents/models.py:101-118` | Refactor `validate_query` |
| `dataing/tests/unit/agents/test_models.py` | Add query validator tests |

## Reuse Points

- **DO NOT DUPLICATE** `dataing/src/dataing/safety/validator.py:24-105` - use existing `validate_query()` function
- **REUSE** `QueryValidationError` from `dataing/src/dataing/core/exceptions.py:50-62`
- **FOLLOW PATTERN** from existing field_validator decorators in models.py

## Quick Commands

```bash
# Run unit tests for affected files
uv run pytest dataing/tests/unit/agents/test_models.py dataing/tests/unit/safety/test_validator.py -v

# Type check
uv run mypy dataing/src/dataing/agents/models.py dataing/src/dataing/safety/validator.py

# Lint
uv run ruff check dataing/src/dataing/agents/models.py dataing/src/dataing/safety/validator.py
```

## Acceptance Criteria

- [ ] Both validators use sqlglot AST parsing instead of regex for mutation detection
- [ ] Markdown stripping preserved (handles ```sql, ```SQL, ```postgresql, unclosed blocks)
- [ ] MERGE statements are blocked
- [ ] Multi-statement queries are rejected (e.g., `SELECT 1; DROP TABLE x`)
- [ ] LIMIT requirement enforced
- [ ] QueryResponse still requires SELECT
- [ ] All existing tests pass
- [ ] New tests cover all edge cases
- [ ] No false positives for column/table names containing keywords (e.g., `deleted_at`, `update_log`)

## Risks

| Risk | Mitigation |
|------|------------|
| sqlglot parse errors for valid dialect-specific SQL | Default to postgres dialect; document limitation |
| Changed error messages affect LLM retry behavior | Preserve similar error message format |
| Performance regression from AST parsing | Unlikely for single queries; monitor if needed |

## References

- Existing sqlglot validator: `dataing/src/dataing/safety/validator.py`
- ADR for sqlglot safety: `docs/docs/architecture/adr-003-sqlglot-safety.md`
- sqlglot docs: https://sqlglot.com/sqlglot.html
