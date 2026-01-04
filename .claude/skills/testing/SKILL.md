---
name: testing
description: Use this skill to run tests for the dataing backend. Supports unit, integration, and e2e tests with coverage reporting.
---

## Test Structure

```
tests/
├── unit/           # Fast, isolated tests (no external deps)
├── integration/    # Tests with database/external services
├── e2e/            # End-to-end API tests
├── fixtures/       # Shared test fixtures and mocks
└── conftest.py     # Root pytest configuration
```

## Run Commands

All commands run from the **project root** (`/Users/bordumb/workspace/repositories/dataing`).

### Run All Tests (with coverage)

```bash
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest
```

### Run by Test Type

**Unit tests only:**
```bash
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/unit/
```

**Integration tests only:**
```bash
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/integration/
```

**E2E tests only:**
```bash
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/e2e/
```

### Run Specific Tests

**Single test file:**
```bash
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/unit/core/test_orchestrator.py
```

**Single test function:**
```bash
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/unit/core/test_orchestrator.py::test_function_name
```

**Tests matching a pattern:**
```bash
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest -k "test_pattern"
```

### Useful Options

| Option | Description |
|--------|-------------|
| `-v` | Verbose output (already default) |
| `-vv` | Extra verbose with full diffs |
| `-x` | Stop on first failure |
| `--pdb` | Drop into debugger on failure |
| `-s` | Show print statements (no capture) |
| `--tb=short` | Shorter traceback format |
| `--tb=no` | No tracebacks |
| `--lf` | Run only last failed tests |
| `--ff` | Run failed tests first |

**Examples:**

```bash
# Stop on first failure, show prints
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/unit/ -x -s

# Run last failed tests with debugger
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest --lf --pdb

# Quick run without coverage
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/unit/ --no-cov
```

### Coverage Reports

Coverage is enabled by default. For additional formats:

```bash
# HTML coverage report (opens in browser)
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest --cov-report=html && open htmlcov/index.html

# XML coverage (for CI)
cd /Users/bordumb/workspace/repositories/dataing && uv run pytest --cov-report=xml
```

---

## Pytest Configuration

From `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"           # Async tests work automatically
testpaths = ["tests"]           # Test discovery path
addopts = "-v --cov=backend/src/dataing --cov-report=term-missing"
```

## Writing Tests

### Async Tests

Async tests work automatically (no `@pytest.mark.asyncio` needed):

```python
async def test_something():
    result = await some_async_function()
    assert result == expected
```

### Using Fixtures

Fixtures in `tests/fixtures/` provide:
- `domain_objects.py` - Sample domain objects (alerts, hypotheses, evidence)
- `mocks.py` - Mock adapters for database, LLM, etc.

Import in conftest.py or test files:

```python
from tests.fixtures.domain_objects import sample_alert
from tests.fixtures.mocks import MockDatabaseAdapter
```

---

## Workflow

1. **Before committing**: Run unit tests
   ```bash
   cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/unit/ -x
   ```

2. **Full test suite**: Run all tests before PR
   ```bash
   cd /Users/bordumb/workspace/repositories/dataing && uv run pytest
   ```

3. **Debugging a failure**: Run with debugger
   ```bash
   cd /Users/bordumb/workspace/repositories/dataing && uv run pytest tests/path/to/test.py::test_name --pdb -s
   ```
