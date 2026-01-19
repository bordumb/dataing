"""Pytest configuration for dataing (CE) tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add CE package to path for imports
ce_src = Path(__file__).parent.parent / "src"
if str(ce_src) not in sys.path:
    sys.path.insert(0, str(ce_src))

# Add tests directory to path for fixture imports
tests_dir = Path(__file__).parent
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))

# Re-export all fixtures from fixtures modules
from fixtures.api_keys import *  # noqa: F401, F403, E402
from fixtures.data_sources import *  # noqa: F401, F403, E402
from fixtures.domain_objects import *  # noqa: F401, F403, E402
from fixtures.mocks import *  # noqa: F401, F403, E402


@pytest.fixture
def anyio_backend() -> str:
    """Configure anyio to use asyncio backend."""
    return "asyncio"
