"""Pytest configuration for dataing-ee tests."""

import sys
from pathlib import Path

import pytest

# Add EE package to path for imports
ee_src = Path(__file__).parent.parent / "src"
if str(ee_src) not in sys.path:
    sys.path.insert(0, str(ee_src))

# Add CE package to path for imports
ce_src = Path(__file__).parent.parent.parent / "dataing" / "src"
if str(ce_src) not in sys.path:
    sys.path.insert(0, str(ce_src))


@pytest.fixture
def anyio_backend() -> str:
    """Configure anyio to use asyncio backend."""
    return "asyncio"
