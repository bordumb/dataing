"""Shared fixtures for CE integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATE_SCRIPT = Path(__file__).resolve().parents[4] / "infra" / "init-app-db.sh"
DEFAULT_DATABASE_URL = "postgresql://dataing:dataing@localhost:5432/dataing_demo"

Migrate = Callable[..., subprocess.CompletedProcess[str]]


def _psql(psql: str, dsn: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run psql against a DSN, ignoring any ~/.psqlrc."""
    return subprocess.run(
        [psql, "--no-psqlrc", "--quiet", dsn, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _migrate(
    dsn: str, migrations_dir: Path = MIGRATIONS_DIR, **env: str
) -> subprocess.CompletedProcess[str]:
    """Run infra/init-app-db.sh, the runner every deployment uses, against dsn.

    Extra keyword arguments are set as environment variables for the runner,
    e.g. INCLUDE_SEEDS="true". Runner settings in the caller's environment are
    ignored, so a developer's shell can't change what the tests apply.
    """
    runner_env = {
        name: value
        for name, value in os.environ.items()
        if name not in {"INCLUDE_SEEDS", "MIGRATIONS_BASELINE"}
    }
    runner_env.update(DATABASE_URL=dsn, MIGRATIONS_DIR=str(migrations_dir), **env)
    return subprocess.run(
        ["bash", str(MIGRATE_SCRIPT)],
        env=runner_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


@contextmanager
def _throwaway_database(psql: str) -> Iterator[str]:
    """Create an empty database on the DATABASE_URL server, dropped on exit."""
    server_dsn = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    database = f"dataing_test_{uuid4().hex[:12]}"
    created = _psql(psql, server_dsn, "--command", f'CREATE DATABASE "{database}"')
    if created.returncode != 0:
        pytest.fail(
            f"Cannot create a test database on the DATABASE_URL server "
            f"(run `just demo-infra` or set DATABASE_URL): {created.stderr.strip()}",
            pytrace=False,
        )
    try:
        yield urlsplit(server_dsn)._replace(path=f"/{database}").geturl()
    finally:
        _psql(psql, server_dsn, "--command", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


@pytest.fixture(scope="session")
def psql() -> str:
    """Path to psql.

    Integration tests only run when selected with `-m integration`, so a missing
    psql or database server fails them instead of skipping them: a skip would let
    CI pass without testing anything.
    """
    path = shutil.which("psql")
    if path is None:
        pytest.fail("psql must be on PATH to apply migrations", pytrace=False)
    return path


@pytest.fixture
def empty_dsn(psql: str) -> Iterator[str]:
    """DSN of a new, empty database, dropped after the test."""
    with _throwaway_database(psql) as dsn:
        yield dsn


@pytest.fixture
def migrate() -> Migrate:
    """Callable that runs infra/init-app-db.sh; see _migrate for its arguments."""
    return _migrate


@pytest.fixture(scope="session")
def migrated_dsn(psql: str) -> Iterator[str]:
    """DSN of a throwaway database built from every schema migration.

    The schema is built by infra/init-app-db.sh, the runner every deployment
    uses, seed files skipped. The runner stops at the first statement that
    fails, so a broken migration fails CI rather than leaving the schema short.
    The database is created on the server in DATABASE_URL and dropped afterwards.
    """
    with _throwaway_database(psql) as dsn:
        migrated = _migrate(dsn)
        if migrated.returncode != 0:
            raise RuntimeError(
                f"infra/init-app-db.sh could not migrate the test database:\n"
                f"{migrated.stdout}{migrated.stderr}"
            )
        yield dsn


@pytest.fixture
async def migrated_db(migrated_dsn: str) -> AsyncIterator[AppDatabase]:
    """AppDatabase connected to the freshly migrated database."""
    db = AppDatabase(dsn=migrated_dsn)
    await db.connect()
    yield db
    await db.close()
