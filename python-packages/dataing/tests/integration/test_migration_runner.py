"""Integration tests for infra/init-app-db.sh, the migration runner.

Each test runs the real script against its own empty database. Most tests use a
small migrations directory written for the test, so they pin down the runner's
rules without depending on the application schema. The tests at the end run the
real migrations.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
Migrate = Callable[..., subprocess.CompletedProcess[str]]

TENANTS = "CREATE TABLE tenants (id int PRIMARY KEY);"
# Drops and recreates a table, as 007 and 013 do with users and investigations.
RECREATE_USERS = "DROP TABLE IF EXISTS users;\nCREATE TABLE users (id int PRIMARY KEY);"
SEED = re.compile(r"[0-9]+_seed_")


def _schema_files() -> list[str]:
    """The real schema migrations (seed files excluded), in the order they apply."""
    return sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql") if not SEED.match(p.name))


def _query(psql: str, dsn: str, sql: str) -> str:
    """Run SQL with psql and return its unaligned, tuples-only output."""
    result = subprocess.run(
        [psql, "--no-psqlrc", "--quiet", "--tuples-only", "--no-align", dsn]
        + ["--set", "ON_ERROR_STOP=1", "--command", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _applied(psql: str, dsn: str) -> list[str]:
    """Filenames recorded in schema_migrations, in byte order like the runner's."""
    return _query(
        psql, dsn, 'SELECT filename FROM schema_migrations ORDER BY filename COLLATE "C"'
    ).split()


def _exists(psql: str, dsn: str, table: str) -> bool:
    """Whether a table exists in the public schema."""
    return _query(psql, dsn, f"SELECT to_regclass('public.{table}') IS NOT NULL") == "t"


def _write_migrations(directory: Path, files: dict[str, str]) -> Path:
    """Write migration files into directory, creating it if needed."""
    directory.mkdir(exist_ok=True)
    for name, sql in files.items():
        (directory / name).write_text(sql)
    return directory


def test_fresh_database_applies_every_file_and_records_it(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Every file runs, in name order, and is recorded in schema_migrations."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "002_users.sql": "CREATE TABLE users (tenant_id int REFERENCES tenants (id));",
            "001_tenants.sql": TENANTS,
        },
    )

    result = migrate(empty_dsn, migrations)

    assert result.returncode == 0, result.stderr
    assert _applied(psql, empty_dsn) == ["001_tenants.sql", "002_users.sql"]
    assert _exists(psql, empty_dsn, "users")


def test_rerun_applies_nothing_and_keeps_data(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """A second run skips applied files, so a file that recreates a table keeps its rows."""
    migrations = _write_migrations(
        tmp_path / "migrations", {"001_tenants.sql": TENANTS, "002_users.sql": RECREATE_USERS}
    )
    assert migrate(empty_dsn, migrations).returncode == 0
    _query(psql, empty_dsn, "INSERT INTO users VALUES (1)")

    rerun = migrate(empty_dsn, migrations)

    assert rerun.returncode == 0, rerun.stderr
    assert _query(psql, empty_dsn, "SELECT count(*) FROM users") == "1"


def test_file_added_later_applies_on_next_run(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Only the new file runs on the next run."""
    migrations = _write_migrations(tmp_path / "migrations", {"001_tenants.sql": TENANTS})
    assert migrate(empty_dsn, migrations).returncode == 0
    _write_migrations(migrations, {"002_users.sql": RECREATE_USERS})

    result = migrate(empty_dsn, migrations)

    assert result.returncode == 0, result.stderr
    assert _applied(psql, empty_dsn) == ["001_tenants.sql", "002_users.sql"]
    assert _exists(psql, empty_dsn, "users")


def test_failing_file_is_rolled_back_and_stops_the_run(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """A failing file keeps none of its changes, isn't recorded, and later files don't run."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "001_tenants.sql": TENANTS,
            "002_broken.sql": "CREATE TABLE users (id int PRIMARY KEY);\nSELECT 1 / 0;",
            "003_later.sql": "CREATE TABLE later (id int PRIMARY KEY);",
        },
    )

    result = migrate(empty_dsn, migrations)

    assert result.returncode != 0
    assert "002_broken.sql" in result.stderr
    assert _applied(psql, empty_dsn) == ["001_tenants.sql"]
    assert not _exists(psql, empty_dsn, "users")
    assert not _exists(psql, empty_dsn, "later")


def test_seed_files_are_skipped_by_default(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Files with "seed" in the name only run when INCLUDE_SEEDS=true."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {"001_tenants.sql": TENANTS, "002_seed_demo.sql": "INSERT INTO tenants VALUES (1);"},
    )

    result = migrate(empty_dsn, migrations)

    assert result.returncode == 0, result.stderr
    assert _applied(psql, empty_dsn) == ["001_tenants.sql"]
    assert _query(psql, empty_dsn, "SELECT count(*) FROM tenants") == "0"


def test_included_seed_files_apply_once(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Seeds included after the schema exists apply on that run and never again."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        # No ON CONFLICT: applying this seed twice fails on the primary key.
        {"001_tenants.sql": TENANTS, "002_seed_demo.sql": "INSERT INTO tenants VALUES (1);"},
    )
    assert migrate(empty_dsn, migrations).returncode == 0

    seeded = migrate(empty_dsn, migrations, INCLUDE_SEEDS="true")
    reseeded = migrate(empty_dsn, migrations, INCLUDE_SEEDS="true")

    assert seeded.returncode == 0, seeded.stderr
    assert reseeded.returncode == 0, reseeded.stderr
    assert _applied(psql, empty_dsn) == ["001_tenants.sql", "002_seed_demo.sql"]
    assert _query(psql, empty_dsn, "SELECT count(*) FROM tenants") == "1"


def test_refuses_database_migrated_before_tracking(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """A database with tables but no migration history is left untouched."""
    _query(psql, empty_dsn, f"{TENANTS} INSERT INTO tenants VALUES (1);")
    migrations = _write_migrations(
        tmp_path / "migrations",
        {"001_tenants.sql": f"DROP TABLE IF EXISTS tenants;\n{TENANTS}"},
    )

    result = migrate(empty_dsn, migrations)

    assert result.returncode != 0
    assert "docker compose down -v" in result.stderr
    assert "MIGRATIONS_BASELINE" in result.stderr
    assert _query(psql, empty_dsn, "SELECT count(*) FROM tenants") == "1"
    assert not _exists(psql, empty_dsn, "schema_migrations")


def test_baseline_adopts_database_migrated_before_tracking(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Files up to the baseline are recorded without running; later ones apply."""
    _query(psql, empty_dsn, f"{TENANTS} INSERT INTO tenants VALUES (1);")
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "001_tenants.sql": f"DROP TABLE IF EXISTS tenants;\n{TENANTS}",
            "002_seed_demo.sql": "INSERT INTO tenants VALUES (2);",
            "003_users.sql": RECREATE_USERS,
        },
    )

    result = migrate(empty_dsn, migrations, MIGRATIONS_BASELINE="002_seed_demo.sql")

    assert result.returncode == 0, result.stderr
    assert _query(psql, empty_dsn, "SELECT id FROM tenants") == "1"
    assert _applied(psql, empty_dsn) == ["001_tenants.sql", "003_users.sql"]
    assert _exists(psql, empty_dsn, "users")


def test_baseline_must_name_a_migration_file(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """A mistyped baseline adopts nothing."""
    _query(psql, empty_dsn, TENANTS)
    migrations = _write_migrations(tmp_path / "migrations", {"001_tenants.sql": TENANTS})

    result = migrate(empty_dsn, migrations, MIGRATIONS_BASELINE="001_tenant.sql")

    assert result.returncode != 0
    assert "001_tenant.sql" in result.stderr
    assert not _exists(psql, empty_dsn, "schema_migrations")


def test_baseline_is_ignored_on_an_empty_database(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """An empty database gets every file applied even if a baseline is set."""
    migrations = _write_migrations(tmp_path / "migrations", {"001_tenants.sql": TENANTS})

    result = migrate(empty_dsn, migrations, MIGRATIONS_BASELINE="001_tenants.sql")

    assert result.returncode == 0, result.stderr
    assert _exists(psql, empty_dsn, "tenants")


def test_files_apply_in_byte_order_whatever_the_locale(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """en_US.UTF-8 sorts 001_memory_rls.sql before 001_memory.sql; the runner must not."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "001_memory.sql": "CREATE TABLE memory (id int PRIMARY KEY);",
            "001_memory_rls.sql": "ALTER TABLE memory ADD COLUMN owner int;",
        },
    )

    result = migrate(empty_dsn, migrations, LC_ALL="en_US.UTF-8")

    assert result.returncode == 0, result.stderr
    assert _applied(psql, empty_dsn) == ["001_memory.sql", "001_memory_rls.sql"]


def test_history_lives_where_search_path_puts_the_schema(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """With a schema named after the user, tables and history land there, and a rerun works."""
    _query(psql, empty_dsn, "CREATE SCHEMA AUTHORIZATION CURRENT_USER")
    migrations = _write_migrations(tmp_path / "migrations", {"001_tenants.sql": TENANTS})
    assert migrate(empty_dsn, migrations).returncode == 0

    rerun = migrate(empty_dsn, migrations)

    assert rerun.returncode == 0, rerun.stderr
    assert _applied(psql, empty_dsn) == ["001_tenants.sql"]


def test_client_side_error_keeps_nothing_from_the_file(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """A failing psql meta-command rolls back the statements before it, too."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "001_tenants.sql": TENANTS,
            "002_broken.sql": (
                "CREATE TABLE users (id int PRIMARY KEY);\n"
                "\\i /nonexistent/migration.sql\n"
                "CREATE TABLE later (id int PRIMARY KEY);"
            ),
        },
    )

    result = migrate(empty_dsn, migrations)

    assert result.returncode != 0
    assert _applied(psql, empty_dsn) == ["001_tenants.sql"]
    assert not _exists(psql, empty_dsn, "users")


def test_file_with_its_own_transaction_control_is_refused(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """BEGIN/COMMIT in a file would end the runner's transaction, so nothing runs."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "001_tenants.sql": TENANTS,
            "002_users.sql": "BEGIN;\nCREATE TABLE users (id int PRIMARY KEY);\nCOMMIT;",
        },
    )

    result = migrate(empty_dsn, migrations)

    assert result.returncode != 0
    assert "002_users.sql" in result.stderr
    assert not _exists(psql, empty_dsn, "tenants")
    assert not _exists(psql, empty_dsn, "users")


def test_seed_files_apply_after_every_schema_file(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Seeds run against the latest schema, whether included on the first run or later."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "001_tenants.sql": TENANTS,
            "002_seed_demo.sql": "INSERT INTO tenants (id, name) VALUES (1, 'demo');",
            "003_tenant_names.sql": "ALTER TABLE tenants ADD COLUMN name text;",
        },
    )

    result = migrate(empty_dsn, migrations, INCLUDE_SEEDS="true")

    assert result.returncode == 0, result.stderr
    assert _query(psql, empty_dsn, "SELECT name FROM tenants") == "demo"


def test_only_numbered_seed_files_are_seeds(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """A schema file that merely mentions "seed" still applies by default."""
    migrations = _write_migrations(
        tmp_path / "migrations",
        {
            "001_tenants.sql": TENANTS,
            "002_add_seed_column.sql": "ALTER TABLE tenants ADD COLUMN seed int;",
        },
    )

    result = migrate(empty_dsn, migrations)

    assert result.returncode == 0, result.stderr
    assert _applied(psql, empty_dsn) == ["001_tenants.sql", "002_add_seed_column.sql"]


def test_unsupported_file_name_is_refused(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """File names are inlined into SQL, so only a safe character set is accepted."""
    migrations = _write_migrations(tmp_path / "migrations", {"001 tenants.sql": TENANTS})

    result = migrate(empty_dsn, migrations)

    assert result.returncode != 0
    assert "001 tenants.sql" in result.stderr
    assert not _exists(psql, empty_dsn, "tenants")


def test_baseline_is_ignored_once_migrations_are_recorded(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """A baseline left set after adoption changes nothing."""
    migrations = _write_migrations(
        tmp_path / "migrations", {"001_tenants.sql": TENANTS, "002_users.sql": RECREATE_USERS}
    )
    assert migrate(empty_dsn, migrations).returncode == 0

    result = migrate(empty_dsn, migrations, MIGRATIONS_BASELINE="001_tenants.sql")

    assert result.returncode == 0, result.stderr
    assert "Ignoring MIGRATIONS_BASELINE" in result.stdout
    assert _applied(psql, empty_dsn) == ["001_tenants.sql", "002_users.sql"]


def test_missing_pg_isready_is_reported(
    tmp_path: Path, empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Without pg_isready on PATH the runner says so instead of waiting for the server."""
    tools = tmp_path / "bin"
    tools.mkdir()
    for tool in ("bash", "psql"):
        found = shutil.which(tool)
        assert found is not None
        os.symlink(found, tools / tool)
    migrations = _write_migrations(tmp_path / "migrations", {"001_tenants.sql": TENANTS})

    result = migrate(empty_dsn, migrations, PATH=str(tools))

    assert result.returncode != 0
    assert "pg_isready" in result.stderr
    assert "Waiting" not in result.stdout


def test_real_migrations_rerun_keeps_users_investigations_and_foreign_keys(
    empty_dsn: str, migrate: Migrate, psql: str
) -> None:
    """Regression: re-running used to empty users and investigations and drop 28 FKs."""
    assert migrate(empty_dsn).returncode == 0
    assert _applied(psql, empty_dsn) == _schema_files()
    tenant, user = "00000000-0000-0000-0000-0000000000a1", "00000000-0000-0000-0000-0000000000b1"
    _query(
        psql,
        empty_dsn,
        f"""
        INSERT INTO tenants (id, name, slug) VALUES ('{tenant}', 't', 't');
        INSERT INTO organizations (id, name, slug) VALUES ('{tenant}', 'o', 'o');
        INSERT INTO users (id, email) VALUES ('{user}', 'u@example.com');
        INSERT INTO org_memberships (user_id, org_id) VALUES ('{user}', '{tenant}');
        INSERT INTO investigations (tenant_id, alert, created_by)
            VALUES ('{tenant}', '{{}}', '{user}');
        """,
    )
    foreign_keys = "SELECT count(*) FROM pg_constraint WHERE contype = 'f'"
    before = _query(psql, empty_dsn, foreign_keys)

    rerun = migrate(empty_dsn)

    assert rerun.returncode == 0, rerun.stderr
    assert _query(psql, empty_dsn, "SELECT count(*) FROM users") == "1"
    assert _query(psql, empty_dsn, "SELECT count(*) FROM investigations") == "1"
    assert _query(psql, empty_dsn, foreign_keys) == before


def test_real_seeds_apply_with_include_seeds(empty_dsn: str, migrate: Migrate, psql: str) -> None:
    """The demo seeds apply strictly on top of the real schema."""
    result = migrate(empty_dsn, INCLUDE_SEEDS="true")

    assert result.returncode == 0, result.stderr
    assert _query(psql, empty_dsn, "SELECT email FROM users") == "demo@dataing.io"


def test_migrated_dsn_is_built_by_the_runner(migrated_dsn: str, psql: str) -> None:
    """Integration tests run on a schema built the same way as every deployment's."""
    assert _applied(psql, migrated_dsn) == _schema_files()
