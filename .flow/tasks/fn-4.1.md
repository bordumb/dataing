# fn-4.1 DataRegistry and AnalysisSandbox implementation

## Description

Create the foundation for LLM to interact with data via code execution rather than seeing raw data in prompts.

### DataRegistry Class

Create `backend/src/dataing/core/investigation/sandbox/registry.py`:

```python
class DataRegistry:
    """Holds pd.DataFrame objects mapped to unique string IDs."""

    def register(self, data: pd.DataFrame, name: str) -> str:
        """Register a DataFrame with a name. Returns the registry ID."""

    def get(self, name: str) -> pd.DataFrame | None:
        """Get DataFrame by name."""

    def list_names(self) -> list[str]:
        """List all registered DataFrame names."""

    def schema(self, name: str) -> dict[str, str]:
        """Get column names and dtypes for a DataFrame."""
```

### AnalysisSandbox Class

Create `backend/src/dataing/core/investigation/sandbox/sandbox.py`:

```python
class AnalysisSandbox:
    """Executes Python code against registered DataFrames."""

    def __init__(self, registry: DataRegistry, max_output_chars: int = 1000):
        """Initialize sandbox with a DataRegistry."""

    def execute(self, code: str) -> ExecutionResult:
        """Run Python code and capture stdout/return value.

        Truncates output if exceeds max_output_chars.
        Raises SandboxExecutionError on failure.
        """
```

### ExecutionResult Type

```python
@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    return_value: str  # JSON-serialized or repr()
    truncated: bool
    execution_time_ms: int
```

### Key Implementation Notes

- Use `exec()` with restricted globals (inject only registered DataFrames + pandas/numpy)
- Capture stdout via `io.StringIO` redirect
- Serialize return value with `json.dumps()` if possible, else `repr()`
- Truncate combined output to `max_output_chars` (default 1000)

### Files to Create

- `backend/src/dataing/core/investigation/sandbox/__init__.py`
- `backend/src/dataing/core/investigation/sandbox/registry.py`
- `backend/src/dataing/core/investigation/sandbox/sandbox.py`
- `backend/src/dataing/core/investigation/sandbox/types.py`
- `backend/tests/unit/core/investigation/sandbox/test_registry.py`
- `backend/tests/unit/core/investigation/sandbox/test_sandbox.py`

### References

- Pattern: Follow frozen dataclass style from `core/domain_types.py:35`
- Naming: Follow existing module structure in `core/investigation/`
## Acceptance
- [ ] `DataRegistry` class created with `register()`, `get()`, `list_names()`, `schema()` methods
- [ ] `AnalysisSandbox` class created with `execute(code: str) -> ExecutionResult` method
- [ ] `ExecutionResult` frozen dataclass with stdout, return_value, truncated, execution_time_ms
- [ ] Output truncation works when result exceeds 1000 chars (configurable)
- [ ] Sandbox injects registered DataFrames into exec() namespace
- [ ] Unit tests: register/retrieve DataFrame, execute simple code, output truncation
- [ ] mypy --strict passes on new sandbox module
- [ ] ruff check passes on new sandbox module
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
