# fn-9.1 Add exp.Merge to FORBIDDEN_STATEMENTS

## Description

Add `exp.Merge` to the `FORBIDDEN_STATEMENTS` set in `dataing/src/dataing/safety/validator.py:37`.

The current regex validator in `models.py` blocks MERGE statements, but the sqlglot-based validator is missing this. This must be fixed before refactoring the Pydantic validators.

**File**: `dataing/src/dataing/safety/validator.py`
**Line**: ~37 (FORBIDDEN_STATEMENTS set)

```python
# Current (missing Merge):
FORBIDDEN_STATEMENTS = {exp.Insert, exp.Update, exp.Delete, ...}

# After (add Merge):
FORBIDDEN_STATEMENTS = {exp.Insert, exp.Update, exp.Delete, exp.Merge, ...}
```

## Acceptance

- [ ] `exp.Merge` added to FORBIDDEN_STATEMENTS set
- [ ] Existing safety validator tests still pass
- [ ] `uv run pytest dataing/tests/unit/safety/test_validator.py -v` passes

## Done summary
- Added `exp.Merge` to FORBIDDEN_STATEMENTS set in safety/validator.py
- Added "MERGE" to FORBIDDEN_KEYWORDS for defense in depth
- Aligns sqlglot validator with regex validator in models.py
- All 35 existing safety validator tests pass
- Lint and type checks pass
## Evidence
- Commits: 48a9195a8194fccadfd15604ae83608affb92435
- Tests: uv run pytest dataing/tests/unit/safety/test_validator.py -v
- PRs:
