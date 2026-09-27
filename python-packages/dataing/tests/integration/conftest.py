"""Shared fixtures for CE integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
DEFAULT_DATABASE_URL = "postgresql://dataing:dataing@localhost:5432/dataing_demo"


def _psql(psql: str, dsn: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run psql against a DSN, ignoring any ~/.psqlrc."""
    return subprocess.run(
        [psql, "--no-psqlrc", "--quiet", dsn, *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def migrated_dsn() -> Iterator[str]:
    """DSN of a throwaway database built from every schema migration.

    Migrations are applied with psql in file order, seed files skipped, like
    `just demo-infra` and infra/init-app-db.sh apply them. Unlike those runners,
    ON_ERROR_STOP is set, so a statement that fails fails the fixture instead of
    being skipped: a broken migration fails CI rather than leaving the schema short.
    The database is created on the server in DATABASE_URL and dropped afterwards.

    Integration tests only run when selected with `-m integration`, so a missing
    psql or database server fails them instead of skipping them: a skip would let
    CI pass without testing anything.
    """
    psql = shutil.which("psql")
    if psql is None:
        pytest.fail("psql must be on PATH to apply migrations", pytrace=False)

    server_dsn = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    database = f"dataing_test_{uuid4().hex[:12]}"
    created = _psql(psql, server_dsn, "--command", f'CREATE DATABASE "{database}"')
    if created.returncode != 0:
        pytest.fail(
            f"Cannot create a test database on the DATABASE_URL server "
            f"(run `just demo-infra` or set DATABASE_URL): {created.stderr.strip()}",
            pytrace=False,
        )

    dsn = urlsplit(server_dsn)._replace(path=f"/{database}").geturl()
    try:
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if "seed" in migration.name:
                continue
            applied = _psql(psql, dsn, "--set", "ON_ERROR_STOP=1", "--file", str(migration))
            if applied.returncode != 0:
                raise RuntimeError(f"psql could not apply {migration.name}: {applied.stderr}")
        yield dsn
    finally:
        _psql(psql, server_dsn, "--command", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


@pytest.fixture
async def migrated_db(migrated_dsn: str) -> AsyncIterator[AppDatabase]:
    """AppDatabase connected to the freshly migrated database."""
    db = AppDatabase(dsn=migrated_dsn)
    await db.connect()
    yield db
    await db.close()
