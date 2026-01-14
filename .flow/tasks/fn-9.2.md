# fn-9.2 Add multi-statement detection to validator

## Description

Enhance `validate_query()` in `dataing/src/dataing/safety/validator.py` to detect and reject multi-statement queries like `SELECT 1; DROP TABLE x`.

Currently `sqlglot.parse_one()` only parses the first statement, so a malicious second statement would slip through. Use `sqlglot.parse()` which returns a list, and reject if more than one statement is found.

**File**: `dataing/src/dataing/safety/validator.py`
**Function**: `validate_query()` (lines 24-105)

```python
# Add check for multi-statement queries:
statements = sqlglot.parse(query, dialect=dialect)
if len([s for s in statements if s is not None]) > 1:
    raise QueryValidationError("Multi-statement queries not allowed")
```

## Acceptance

- [ ] Multi-statement queries (e.g., `SELECT 1; DROP TABLE x`) are rejected
- [ ] Single statements with trailing semicolon still work
- [ ] Add test case for multi-statement detection
- [ ] `uv run pytest dataing/tests/unit/safety/test_validator.py -v` passes

## Done summary
- Added multi-statement query detection in validate_query()
- Uses sqlglot.parse() to detect multiple statements before processing
- Added 3 test cases: basic rejection, injection detection, trailing semicolon OK
- All 38 tests pass
- Lint and type checks pass
## Evidence
- Commits: 4deb65e249b281d19bf8d5c5b3ca241ce1d23e00
- Tests: uv run pytest dataing/tests/unit/safety/test_validator.py -v
- PRs:
