# fn-4.4 Tool definitions for RecursiveAnalysisStep

## Description

Define the strict tool API available to the LLM within `RecursiveAnalysisStep`.

### Tool Definitions

Create `backend/src/dataing/core/investigation/sandbox/tools.py`:

```python
@dataclass(frozen=True)
class InspectSchemaResult:
    variable_name: str
    columns: dict[str, str]  # column_name -> dtype
    row_count: int
    sample_values: dict[str, list[Any]]  # First 3 values per column

@dataclass(frozen=True)
class RunPythonResult:
    code: str
    stdout: str
    return_value: str
    truncated: bool
    error: str | None

@dataclass(frozen=True)
class RequestBranchResult:
    branch_id: str
    rationale: str
    filter_condition: str
```

### Tool Implementations

```python
class AnalysisTools:
    """Tools available to RecursiveAnalysisStep."""

    def __init__(self, sandbox: AnalysisSandbox, registry: DataRegistry):
        self._sandbox = sandbox
        self._registry = registry

    def inspect_schema(self, variable_name: str) -> InspectSchemaResult:
        """Get schema info for a registered DataFrame."""

    def run_python_analysis(self, code: str) -> RunPythonResult:
        """Execute Python code in sandbox."""

    def request_branch(
        self, rationale: str, filter_condition: str
    ) -> RequestBranchResult:
        """Request a child branch with filtered data."""
```

### LLM Tool Schema

Format tools for Claude's tool_use API:

```python
ANALYSIS_TOOLS = [
    {
        "name": "inspect_schema",
        "description": "Get column names, types, and sample values for a data variable",
        "input_schema": {
            "type": "object",
            "properties": {
                "variable_name": {"type": "string"}
            },
            "required": ["variable_name"]
        }
    },
    {
        "name": "run_python_analysis",
        "description": "Execute Python code to analyze data. Use pandas operations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"}
            },
            "required": ["code"]
        }
    },
    {
        "name": "request_branch",
        "description": "Spawn a child investigation on a data subset",
        "input_schema": {
            "type": "object",
            "properties": {
                "rationale": {"type": "string"},
                "filter_condition": {"type": "string"}
            },
            "required": ["rationale", "filter_condition"]
        }
    }
]
```

### Files to Create

- `backend/src/dataing/core/investigation/sandbox/tools.py`
- `backend/tests/unit/core/investigation/sandbox/test_tools.py`

### References

- Claude tool_use: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
## Acceptance
- [ ] `InspectSchemaResult`, `RunPythonResult`, `RequestBranchResult` dataclasses created
- [ ] `AnalysisTools` class with `inspect_schema()`, `run_python_analysis()`, `request_branch()` methods
- [ ] `ANALYSIS_TOOLS` schema constant for Claude tool_use API
- [ ] `inspect_schema` returns column names, dtypes, row count, sample values
- [ ] `run_python_analysis` delegates to AnalysisSandbox.execute()
- [ ] `request_branch` creates BranchRequest with filter condition
- [ ] Unit tests for each tool
- [ ] mypy --strict passes
- [ ] ruff check passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
