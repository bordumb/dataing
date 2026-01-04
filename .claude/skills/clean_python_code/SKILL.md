---
name: clean-python-code
description: Use this skill after writing or modifying Python code in ./backend/src/dataing/ to ensure it passes all pre-commit checks.
---

## Run These Commands

Run these commands in order:

**1. Fix all ruff issues (including unsafe fixes):**
```bash
cd /Users/bordumb/workspace/repositories/dataing/backend && uv run ruff check src/dataing/ --unsafe-fixes --fix
```

**2. Verify no errors remain (run WITHOUT --fix to see all issues):**
```bash
cd /Users/bordumb/workspace/repositories/dataing/backend && uv run ruff check src/dataing/
```

**3. Run mypy:**
```bash
cd /Users/bordumb/workspace/repositories/dataing/backend && uv run mypy src/dataing/
```

Fix any errors reported, then re-run until all three pass.

---

## Ruff Rules (Line Length: 100 chars)

### Import Sorting (I - isort)
```python
# CORRECT: stdlib, then third-party, then local, alphabetized
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from dataing.core.domain_types import AnomalyAlert
from dataing.adapters.lineage import DatasetId
```

### Docstrings (D - pydocstyle, Google convention)

Every public module, class, method, and function needs a docstring:

```python
# D102: Missing docstring in public method
# D107: Missing docstring in __init__

class MyClass:
    """Brief description of the class."""

    def __init__(self, value: int) -> None:
        """Initialize the class.

        Args:
            value: The initial value.
        """
        self.value = value

    def process(self, data: str) -> str:
        """Process the input data.

        Args:
            data: Input string to process.

        Returns:
            Processed string result.
        """
        return data.upper()
```

### Line Length (E501)
```python
# BAD: Line over 100 characters
result = some_very_long_function_name(first_argument, second_argument, third_argument, fourth_argument)

# GOOD: Break across lines
result = some_very_long_function_name(
    first_argument,
    second_argument,
    third_argument,
    fourth_argument,
)
```

### Modern Python (UP - pyupgrade)
```python
# BAD: Old-style union
def foo(x: Union[int, str]) -> Optional[list]:

# GOOD: Modern syntax (Python 3.10+)
def foo(x: int | str) -> list | None:

# BAD: Old isinstance
if isinstance(x, (int, str)):

# GOOD: Modern isinstance
if isinstance(x, int | str):
```

### Exception Handling (B904)
```python
# BAD: Raise without chaining
try:
    do_something()
except ValueError as e:
    raise RuntimeError("Failed")  # B904 error

# GOOD: Chain exceptions
try:
    do_something()
except ValueError as e:
    raise RuntimeError("Failed") from e

# GOOD: Explicitly suppress chain
try:
    do_something()
except ValueError:
    raise RuntimeError("Failed") from None
```

### Unused Variables (F841)
```python
# BAD: Unused variable
result = some_function()  # F841 if result is never used

# GOOD: Use underscore for intentionally unused
_ = some_function()

# GOOD: Multiple unused
_ = (unused_var1, unused_var2, unused_var3)
```

### Unused Imports (F401)
```python
# BAD: Import not used
from typing import Optional  # F401 if Optional never used

# GOOD: Only import what you use, or mark as re-export
from typing import Optional  # noqa: F401 (if intentionally re-exporting)
```

---

## Mypy Rules (Strict Mode)

### All Functions Need Type Annotations (disallow_untyped_defs)
```python
# BAD: No return type
def process(data):
    return data.upper()

# GOOD: Full annotations
def process(data: str) -> str:
    return data.upper()

# GOOD: For methods that return None
def setup(self) -> None:
    self.initialized = True
```

### No Returning Any (warn_return_any)
```python
# BAD: Returns Any implicitly
def get_value(data: dict[str, Any]) -> str:
    return data.get("key")  # Returns Any

# GOOD: Explicit type annotation
def get_value(data: dict[str, Any]) -> str:
    result: str = data.get("key", "")
    return result

# GOOD: Cast if necessary
from typing import cast
def get_value(data: dict[str, Any]) -> str:
    return cast(str, data.get("key"))
```

### Generic Types Need Parameters (disallow_any_generics)
```python
# BAD: Unparameterized generics
def process(items: list) -> dict:

# GOOD: Specify type parameters
def process(items: list[str]) -> dict[str, int]:

# GOOD: Use Any explicitly when needed
def process(items: list[Any]) -> dict[str, Any]:
```

### Nested Functions and Closures

When a variable is checked for None in outer scope but used in inner function, mypy may not recognize the narrowing:

```python
# BAD: mypy error in nested function
def outer(self) -> list[str]:
    if self._data is None:
        return []

    def inner() -> str:
        return self._data.get("key")  # Error: Item "None" has no attribute "get"

    return [inner()]

# GOOD: Assign to local variable before closure
def outer(self) -> list[str]:
    data = self._data
    if data is None:
        return []

    def inner() -> str:
        return data.get("key")  # Works: data is definitely not None

    return [inner()]
```

### Protocol and Abstract Methods
```python
from typing import Protocol, runtime_checkable
from abc import ABC, abstractmethod

@runtime_checkable
class MyProtocol(Protocol):
    """Protocol for type checking."""

    def process(self, data: str) -> str:
        """Process data."""
        ...

class MyBase(ABC):
    """Abstract base class."""

    @abstractmethod
    def process(self, data: str) -> str:
        """Process data. Must be implemented by subclasses."""
        ...
```

### External Libraries Without Types
```python
# For untyped library calls, add type: ignore comment
result = untyped_library.function()  # type: ignore[no-untyped-call]

# Or annotate the result explicitly
result: str = untyped_library.function()
```

### Pydantic Models
```python
from pydantic import BaseModel, ConfigDict, Field

class MyModel(BaseModel):
    """Model with proper typing."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: int = Field(default=0, ge=0)
    items: list[str] = Field(default_factory=list)
```

### Dataclasses
```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class MyData:
    """Immutable data class."""

    name: str
    values: list[int] = field(default_factory=list)
```

---

## Quick Fixes Reference

| Error Code | Issue | Fix |
|------------|-------|-----|
| D102 | Missing method docstring | Add `"""Brief description."""` |
| D107 | Missing `__init__` docstring | Add `"""Initialize the class."""` |
| E501 | Line too long (>100) | Break into multiple lines |
| F401 | Unused import | Remove or add `# noqa: F401` |
| F841 | Unused variable | Use `_` or remove |
| B904 | Raise without `from` | Add `from e` or `from None` |
| UP038 | Old isinstance syntax | Use `isinstance(x, A \| B)` |

---

## Verification Commands

After fixing, verify all checks pass:

```bash
# Run ruff with autofix
cd backend && uv run ruff check src/dataing/ --fix

# Run mypy
cd backend && uv run mypy src/dataing/

# Run full pre-commit
pre-commit run --all-files
```
