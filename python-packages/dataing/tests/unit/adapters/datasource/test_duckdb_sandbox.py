"""Tests for confining in-process DuckDB connections to a data source's location."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from dataing.adapters.datasource import duckdb_sandbox


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """A data source directory, with files outside it that must stay unreadable."""
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "orders.csv").write_text("id,amount\n1,10\n2,20\n")
    (src / "sub" / "items.csv").write_text("id\n7\n")
    (tmp_path / "outside.csv").write_text("secret\nleaked\n")
    (tmp_path / "src-sibling").mkdir()
    (tmp_path / "src-sibling" / "other.csv").write_text("secret\nleaked\n")
    return src


@pytest.fixture
def conn(source_dir: Path) -> Iterator[Any]:
    """A connection confined to source_dir."""
    connection = duckdb.connect(":memory:", config=duckdb_sandbox.connection_config())
    duckdb_sandbox.confine(connection, directories=[str(source_dir)])
    yield connection
    connection.close()


class TestConfinedReads:
    """Queries can read the source's own files and nothing else."""

    def test_reads_files_in_the_source_directory(self, conn: Any, source_dir: Path) -> None:
        """A normal query over the source's own file runs."""
        rows = conn.execute(
            f"SELECT * FROM read_csv('{source_dir}/orders.csv') ORDER BY id"
        ).fetchall()
        assert rows == [(1, 10), (2, 20)]

    def test_reads_files_in_subdirectories(self, conn: Any, source_dir: Path) -> None:
        """Files below the source directory are part of the source."""
        rows = conn.execute(f"SELECT * FROM '{source_dir}/sub/items.csv'").fetchall()
        assert rows == [(7,)]

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM read_csv('/etc/passwd') LIMIT 10",
            "SELECT * FROM read_text('/etc/passwd') LIMIT 10",
            "SELECT * FROM read_blob('/etc/passwd') LIMIT 10",
            "SELECT * FROM glob('/etc/*') LIMIT 10",
        ],
    )
    def test_refuses_host_files(self, conn: Any, sql: str) -> None:
        """Files elsewhere on the host are refused, whichever function asks."""
        with pytest.raises(duckdb.PermissionException):
            conn.execute(sql).fetchall()

    @pytest.mark.parametrize(
        "relative_path",
        [
            "../outside.csv",
            "./../outside.csv",
            "sub/../../outside.csv",
            "./" * 16 + "../" * 16 + "etc/passwd",
        ],
    )
    def test_refuses_path_traversal(self, conn: Any, source_dir: Path, relative_path: str) -> None:
        """Paths that start inside the source but resolve outside it are refused."""
        with pytest.raises(duckdb.PermissionException):
            conn.execute(f"SELECT * FROM read_text('{source_dir}/{relative_path}')").fetchall()

    def test_refuses_sibling_directory_sharing_the_prefix(
        self, conn: Any, source_dir: Path
    ) -> None:
        """src-sibling/ is not inside src/ even though the strings share a prefix."""
        with pytest.raises(duckdb.PermissionException):
            conn.execute(f"SELECT * FROM read_text('{source_dir}-sibling/other.csv')").fetchall()

    def test_refuses_urls(self, conn: Any) -> None:
        """Remote files are outside a local source."""
        with pytest.raises(duckdb.PermissionException):
            conn.execute("SELECT * FROM read_csv('https://example.com/data.csv')").fetchall()


class TestConfinedURLPrefix:
    """A connection confined to an s3:// prefix reads under it and nowhere else."""

    @pytest.fixture
    def s3_conn(self) -> Iterator[Any]:
        """A connection confined to s3://acme-data/warehouse/, pointed at a closed local port.

        Reads that pass the sandbox fail at 127.0.0.1:9 without leaving the machine.
        """
        connection = duckdb.connect(":memory:", config=duckdb_sandbox.connection_config())
        try:
            connection.execute("INSTALL httpfs")
            connection.execute("LOAD httpfs")
        except duckdb.Error as e:
            connection.close()
            pytest.skip(f"DuckDB httpfs extension unavailable: {e}")
        connection.execute(
            "CREATE SECRET (TYPE s3, KEY_ID 'key', SECRET 'secret', ENDPOINT '127.0.0.1:9', "
            "USE_SSL false, URL_STYLE 'path')"
        )
        duckdb_sandbox.confine(connection, directories=["s3://acme-data/warehouse/"])
        yield connection
        connection.close()

    def test_reads_under_the_prefix_pass_the_sandbox(self, s3_conn: Any) -> None:
        """Objects under the prefix are fetched (here, from the closed local port)."""
        with pytest.raises(duckdb.IOException, match="127.0.0.1:9"):
            s3_conn.execute("SELECT * FROM read_csv('s3://acme-data/warehouse/orders.csv')")

    @pytest.mark.parametrize(
        "url",
        [
            "s3://acme-data/finance/salaries.csv",
            "s3://acme-data/warehouse-archive/orders.csv",
            "s3://acme-data/warehouse/../finance/salaries.csv",
            "s3://acme-data/warehouse/./../finance/salaries.csv",
            "s3://other-bucket/warehouse/orders.csv",
        ],
    )
    def test_refuses_other_prefixes_and_buckets(self, s3_conn: Any, url: str) -> None:
        """Other prefixes and buckets are refused before any request is made."""
        with pytest.raises(duckdb.PermissionException):
            s3_conn.execute(f"SELECT * FROM read_csv('{url}')")


class TestLockedConfiguration:
    """A confined connection cannot be reconfigured or extended."""

    @pytest.mark.parametrize(
        "statement",
        [
            "SET enable_external_access = true",
            "SET allowed_directories = ['/']",
            "RESET lock_configuration",
        ],
    )
    def test_settings_cannot_be_changed(self, conn: Any, statement: str) -> None:
        """Settings are locked once the connection is confined."""
        with pytest.raises(duckdb.Error, match="locked"):
            conn.execute(statement)

    def test_extensions_cannot_be_loaded(self, conn: Any) -> None:
        """Loading an extension would reach outside the sandbox."""
        with pytest.raises(duckdb.PermissionException):
            conn.execute("LOAD sqlite")


class TestDuckDBVersion:
    """Only DuckDB releases whose allowlist check resolves . and .. can confine."""

    @pytest.mark.parametrize("version", ["0.9.2", "1.4.3", "1.5.0", "1.5.5", "2.0.0"])
    def test_refuses_releases_whose_check_can_be_escaped(
        self, source_dir: Path, monkeypatch: pytest.MonkeyPatch, version: str
    ) -> None:
        """An unsupported DuckDB fails loudly instead of running an escapable sandbox."""
        monkeypatch.setattr(duckdb, "__version__", version)
        connection = duckdb.connect(":memory:", config=duckdb_sandbox.connection_config())
        with pytest.raises(RuntimeError, match=f"DuckDB {version}"):
            duckdb_sandbox.confine(connection, directories=[str(source_dir)])
        connection.close()

    @pytest.mark.parametrize("version", ["1.4.4", "1.4.5", "1.4.6.dev3"])
    def test_accepts_the_1_4_releases_from_1_4_4(
        self, source_dir: Path, monkeypatch: pytest.MonkeyPatch, version: str
    ) -> None:
        """1.4.4 and later 1.4 releases confine the connection."""
        monkeypatch.setattr(duckdb, "__version__", version)
        connection = duckdb.connect(":memory:", config=duckdb_sandbox.connection_config())
        duckdb_sandbox.confine(connection, directories=[str(source_dir)])
        with pytest.raises(duckdb.PermissionException):
            connection.execute("SELECT * FROM read_text('/etc/passwd')").fetchall()
        connection.close()


class TestSpillDirectory:
    """Each connection spills to a temporary directory of its own."""

    def test_shared_spill_directory_is_not_readable(
        self, source_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DuckDB's default spill directory (.tmp in the working directory) is refused.

        DuckDB allowlists its spill directory, so a shared one would let one source's
        queries read other connections' spilled data.
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".tmp").mkdir()
        (tmp_path / ".tmp" / "spill.bin").write_text("another connection's data")
        connection = duckdb.connect(":memory:", config=duckdb_sandbox.connection_config())
        duckdb_sandbox.confine(connection, directories=[str(source_dir)])
        with pytest.raises(duckdb.PermissionException):
            connection.execute("SELECT * FROM read_blob('.tmp/spill.bin')").fetchall()
        connection.close()

    def test_large_queries_still_spill_to_disk(self, source_dir: Path) -> None:
        """Confinement keeps out-of-core execution working."""
        connection = duckdb.connect(":memory:", config=duckdb_sandbox.connection_config())
        connection.execute("SET memory_limit = '32MB'")
        connection.execute("SET threads = 1")
        duckdb_sandbox.confine(connection, directories=[str(source_dir)])
        count = connection.execute(
            "SELECT count(*) FROM (SELECT md5(i::VARCHAR) AS h FROM range(1500000) t(i) ORDER BY h)"
        ).fetchone()
        assert count == (1500000,)
        connection.close()


class TestDatabaseWithoutDirectories:
    """A connection with no allowed directories reads only its own database."""

    def test_reads_its_database_and_no_files(self, tmp_path: Path) -> None:
        """Tables in the attached database stay queryable; files are refused."""
        db_path = tmp_path / "source.duckdb"
        setup = duckdb.connect(str(db_path))
        setup.execute("CREATE TABLE orders AS SELECT 42 AS id")
        setup.close()

        connection = duckdb.connect(
            str(db_path), read_only=True, config=duckdb_sandbox.connection_config()
        )
        duckdb_sandbox.confine(connection, directories=[])
        assert connection.execute("SELECT id FROM orders").fetchall() == [(42,)]
        with pytest.raises(duckdb.PermissionException):
            connection.execute("SELECT * FROM read_text('/etc/passwd')").fetchall()
        connection.close()
