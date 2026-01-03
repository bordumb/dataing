"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest

# Re-export all fixtures from fixtures modules
from tests.fixtures.api_keys import *  # noqa: F401, F403
from tests.fixtures.data_sources import *  # noqa: F401, F403
from tests.fixtures.domain_objects import *  # noqa: F401, F403
from tests.fixtures.mocks import *  # noqa: F401, F403


@pytest.fixture
def anyio_backend() -> str:
    """Configure anyio to use asyncio backend."""
    return "asyncio"
