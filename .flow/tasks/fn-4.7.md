# fn-4.7 Sandbox safety restrictions and code validator

## Description


Ensure the `AnalysisSandbox` cannot damage the host system or escape its boundaries.

### Code Validator

Create `backend/src/dataing/safety/code_validator.py`:

```python
BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "urllib", "requests", "httpx",
    "pickle", "marshal", "shelve",
    "ctypes", "cffi", "multiprocessing",
    "__builtins__", "builtins", "importlib",
})

BLOCKED_CALLS = frozenset({
    "exec", "eval", "compile", "open", "input",
    "__import__", "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
})

def validate_code(code: str) -> ValidationResult:
    """Parse code AST and check for blocked imports/calls."""
```

### AST-Based Validation

```python
import ast

class CodeSecurityVisitor(ast.NodeVisitor):
    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split('.')[0] in BLOCKED_IMPORTS:
                raise BlockedImportError(alias.name)

    def visit_ImportFrom(self, node):
        if node.module and node.module.split('.')[0] in BLOCKED_IMPORTS:
            raise BlockedImportError(node.module)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in BLOCKED_CALLS:
                raise BlockedCallError(node.func.id)
```

### Execution Limits

Integrate with existing CircuitBreaker at `safety/circuit_breaker.py`:

```python
@dataclass
class CodeExecutionLimits:
    max_execution_time_seconds: float = 5.0
    max_memory_mb: int = 256
    max_iterations_per_step: int = 10
    max_branch_depth: int = 3
```

### Sandbox Hardening

In `AnalysisSandbox.execute()`:

```python
# Restricted globals - only safe builtins + pandas + numpy
SAFE_GLOBALS = {
    "__builtins__": {
        "print": print,
        "len": len,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "sorted": sorted,
        "min": min,
        "max": max,
        "sum": sum,
        "abs": abs,
        "round": round,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "True": True,
        "False": False,
        "None": None,
    },
    "pd": pd,
    "np": np,
}
```

### Files to Create/Modify

- `backend/src/dataing/safety/code_validator.py` (new)
- `backend/src/dataing/core/investigation/sandbox/sandbox.py` (add validation + limits)
- `backend/src/dataing/safety/circuit_breaker.py` (add CodeExecutionLimits)
- `backend/tests/unit/safety/test_code_validator.py` (new)

### References

- Query Validator pattern: `safety/validator.py:1-162`
- CircuitBreaker: `safety/circuit_breaker.py:40-179`
## Acceptance
- [ ] `CodeValidator` with AST-based import/call blocking
- [ ] BLOCKED_IMPORTS includes: os, sys, subprocess, socket, pickle, etc.
- [ ] BLOCKED_CALLS includes: exec, eval, open, __import__, etc.
- [ ] Sandbox uses restricted globals (only safe builtins + pd + np)
- [ ] Execution timeout of 5 seconds (configurable)
- [ ] Memory limit integration (256MB default)
- [ ] `CodeExecutionLimits` added to CircuitBreaker
- [ ] Unit test: blocked import raises error
- [ ] Unit test: blocked function call raises error
- [ ] Unit test: timeout on infinite loop
- [ ] Unit test: valid pandas code executes successfully
- [ ] mypy --strict passes
- [ ] ruff check passes
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
