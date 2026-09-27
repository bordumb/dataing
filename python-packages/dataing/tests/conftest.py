"""Pytest configuration for dataing (CE) tests."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
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


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    """Restore the root logger's handlers and level after each test.

    configure_logging() (create_app(), the worker's main()) binds its root handler to
    the current sys.stdout. Inside a test that can be capsys's stream, which is closed
    once the test ends. pytest's own handlers are kept.
    """
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers[:]:
        if handler not in handlers:
            root.removeHandler(handler)
    for handler in handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(level)


@pytest.fixture
def anyio_backend() -> str:
    """Configure anyio to use asyncio backend."""
    return "asyncio"
