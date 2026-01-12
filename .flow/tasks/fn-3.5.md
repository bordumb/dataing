# fn-3.5 Unit tests for all GitHunter methods

## Description
Write comprehensive unit tests for all GitHunter functionality.

**Test files to create:**
- `bond/tests/unit/tools/githunter/__init__.py`
- `bond/tests/unit/tools/githunter/test_types.py`
- `bond/tests/unit/tools/githunter/test_adapter.py`

**Testing approach:**
- Mock `asyncio.create_subprocess_exec` for git CLI calls
- Mock `httpx.AsyncClient` for GitHub API calls
- Use pytest fixtures for common test data

**Test scenarios:**

1. **Types tests:** Dataclass immutability (frozen), field validation

2. **blame_line tests:** Happy path, line out of range, file not found, binary file, shallow clone boundary

3. **find_pr_discussion tests:** Commit with PR, commit without PR, rate limit, no GITHUB_TOKEN

4. **get_expert_for_file tests:** Multiple authors ranked, window days filtering, empty history
## Acceptance
- [ ] Tests for all types (frozen, field types)
- [ ] Tests for blame_line with mocked git subprocess
- [ ] Tests for find_pr_discussion with mocked GitHub API
- [ ] Tests for get_expert_for_file with mocked git log
- [ ] Error case tests for all exception types
- [ ] Edge case tests (shallow clone, no PR, rate limit, no token)
- [ ] All tests pass: `cd bond && uv run pytest tests/unit/tools/githunter/ -v`
- [ ] Coverage > 80% for githunter module
## Done summary
## Summary

Implemented comprehensive unit tests for GitHunter module

### Tests Created
- `bond/tests/unit/tools/githunter/__init__.py`
- `bond/tests/unit/tools/githunter/test_types.py` - 11 tests for frozen dataclasses
- `bond/tests/unit/tools/githunter/test_adapter.py` - 27 tests for adapter methods

### Test Coverage
- 38 tests total
- 87% coverage (exceeds 80% requirement)
- All tests pass

### Test Scenarios Covered
- Types: frozen immutability, field validation
- blame_line: happy path, boundary commit, errors (file not found, line out of range, binary, not a repo)
- find_pr_discussion: happy path, no token, no PR, rate limit, timeout
- get_expert_for_file: multiple authors, limit, empty history, case-insensitive email
- enrich_author: found, not found, no token
- _get_github_repo: SSH URL, HTTPS URL, non-GitHub remote
## Evidence
- Commits: 0ba95340
- Tests: 38_tests_passed, 87_percent_coverage
- PRs:
