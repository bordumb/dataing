# fn-9.6 Add comprehensive tests for query validators

## Description

Add comprehensive tests to `dataing/tests/unit/agents/test_models.py` covering all edge cases identified in gap analysis.

**File**: `dataing/tests/unit/agents/test_models.py`

## Test Cases Required

### Happy Path
- [ ] Valid SELECT with LIMIT passes
- [ ] Valid SELECT with subquery and LIMIT passes

### Markdown Stripping
- [ ] Query wrapped in ```sql ... ``` is stripped
- [ ] Query wrapped in ```SQL ... ``` is stripped
- [ ] Query wrapped in ```postgresql ... ``` is stripped
- [ ] Unclosed markdown block handled gracefully

### Validation Errors
- [ ] Missing LIMIT raises ValueError
- [ ] QueryResponse without SELECT raises ValueError

### Mutation Blocking
- [ ] INSERT blocked
- [ ] UPDATE blocked
- [ ] DELETE blocked
- [ ] DROP blocked
- [ ] TRUNCATE blocked
- [ ] ALTER blocked
- [ ] CREATE blocked
- [ ] MERGE blocked
- [ ] GRANT blocked
- [ ] REVOKE blocked

### False Positive Prevention
- [ ] Column named `deleted_at` allowed
- [ ] Table named `update_log` allowed
- [ ] Column named `created_by` allowed

### Edge Cases
- [ ] Multi-statement query rejected (`SELECT 1; DROP TABLE x`)
- [ ] Empty query after markdown strip raises ValueError
- [ ] CTE with mutation rejected (`WITH x AS (...) DELETE ...`)
- [ ] Subquery with mutation rejected (if dialect supports)

## Acceptance

- [ ] All test cases above implemented and passing
- [ ] Tests use pytest parametrize for mutation keywords
- [ ] Tests cover both HypothesisResponse and QueryResponse validators
- [ ] `uv run pytest dataing/tests/unit/agents/test_models.py -v` passes

## Done summary
- Added 25 comprehensive query validator tests
- Covers: happy path, markdown stripping, validation errors, mutation blocking
- False positive prevention: columns/tables with keyword-like names pass
- Edge cases: multi-statement rejection, empty query handling
- All 77 tests pass (38 validator + 39 model tests)
- Lint and type checks pass
## Evidence
- Commits: 548701828464cb9909da03c15f2304da66d8be2e
- Tests: uv run pytest dataing/tests/unit/agents/test_models.py dataing/tests/unit/safety/test_validator.py -v
- PRs:
