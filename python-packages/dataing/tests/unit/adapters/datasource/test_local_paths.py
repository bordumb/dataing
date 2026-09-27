"""Tests for keeping local data sources inside the operator's local data root."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import duckdb
import pytest

from dataing.adapters.datasource import DuckDBAdapter, LocalFileAdapter, SQLiteAdapter
from dataing.adapters.datasource.errors import InvalidConfigError
from dataing.adapters.datasource.local_paths import resolve_local_path
from dataing.adapters.lineage.adapters.dbt import DbtAdapter

ROOT_ENV = "DATAING_LOCAL_DATA_ROOT"
MANIFEST = {
    "nodes": {
        "model.shop.orders": {
            "name": "orders",
            "resource_type": "model",
            "database": "analytics",
            "schema": "shop",
        }
    }
}


def make_sqlite(path: Path) -> Path:
    """Create a SQLite database at path with one table holding one row."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders AS SELECT 42 AS id")
    conn.commit()
    conn.close()
    return path


def write_manifest(path: Path) -> Path:
    """Write a dbt manifest with one model at path."""
    path.write_text(json.dumps(MANIFEST))
    return path


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set a local data root holding one data directory and a symlink out of it."""
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    (root / "data" / "orders.csv").write_text("id\n1\n2\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secrets.csv").write_text("secret\nleaked\n")
    (root / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv(ROOT_ENV, str(root))
    return root


@pytest.fixture(params=["outside", "filesystem-root", "escaping-symlink", "dot-dot", "prefix"])
def escaping_path(request: pytest.FixtureRequest, root: Path) -> str:
    """A path that resolves outside the local data root."""
    paths = {
        "outside": f"{root.parent}/outside",
        "filesystem-root": "/",
        "escaping-symlink": f"{root}/escape",
        "dot-dot": f"{root}/data/../../outside",
        "prefix": f"{root}-sibling",
    }
    return paths[request.param]


@pytest.fixture
def no_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave the local data root unset."""
    monkeypatch.delenv(ROOT_ENV, raising=False)


class TestResolveLocalPath:
    """A source's path must resolve inside the local data root."""

    def test_resolves_a_path_inside_the_root(self, root: Path) -> None:
        """A path inside the root comes back with symlinks resolved."""
        assert resolve_local_path(f"{root}/data") == os.path.realpath(root / "data")

    def test_refuses_a_path_that_resolves_outside_the_root(self, escaping_path: str) -> None:
        """Paths outside the root are refused, however they get there."""
        with pytest.raises(InvalidConfigError) as exc_info:
            resolve_local_path(escaping_path)
        assert exc_info.value.details == {"field": "path"}

    def test_follows_symlinks_that_stay_inside_the_root(self, root: Path) -> None:
        """A symlink to another place inside the root is allowed."""
        (root / "latest").symlink_to(root / "data", target_is_directory=True)
        assert resolve_local_path(f"{root}/latest") == os.path.realpath(root / "data")

    def test_resolves_a_relative_path_against_the_root(self, root: Path) -> None:
        """A relative path means the same place in every process, whatever its cwd."""
        assert resolve_local_path("data") == os.path.realpath(root / "data")

    def test_refuses_a_relative_path_that_climbs_out(self, root: Path) -> None:
        """A relative path cannot climb out of the root."""
        with pytest.raises(InvalidConfigError):
            resolve_local_path("../outside")

    def test_resolves_the_root_through_its_own_symlinks(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both sides are compared after resolving symlinks."""
        link = root.parent / "root-link"
        link.symlink_to(root, target_is_directory=True)
        monkeypatch.setenv(ROOT_ENV, str(link))
        assert resolve_local_path(f"{root}/data") == os.path.realpath(root / "data")

    @pytest.mark.parametrize("path", ["", None, 42, "data\x00"])
    def test_refuses_a_missing_or_malformed_path(self, root: Path, path: object) -> None:
        """A missing or malformed path is a configuration error, not a crash."""
        with pytest.raises(InvalidConfigError):
            resolve_local_path(path)

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_refuses_every_path_while_the_root_is_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
    ) -> None:
        """Local sources stay off until an operator sets the root."""
        if value is None:
            monkeypatch.delenv(ROOT_ENV, raising=False)
        else:
            monkeypatch.setenv(ROOT_ENV, value)
        with pytest.raises(InvalidConfigError, match=ROOT_ENV):
            resolve_local_path(str(tmp_path))


class TestLocalFileAdapter:
    """The local file adapter checks its path every time it connects."""

    @pytest.mark.asyncio
    async def test_refuses_to_connect_outside_the_root(self, escaping_path: str) -> None:
        """No connection opens for a path outside the root."""
        adapter = LocalFileAdapter({"path": escaping_path})
        with pytest.raises(InvalidConfigError):
            await adapter.connect()
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_refuses_to_connect_while_the_root_is_unset(
        self, tmp_path: Path, no_root: None
    ) -> None:
        """Without a root, local file sources are refused."""
        adapter = LocalFileAdapter({"path": str(tmp_path)})
        with pytest.raises(InvalidConfigError, match=ROOT_ENV):
            await adapter.connect()

    @pytest.mark.asyncio
    async def test_reads_a_directory_inside_the_root(self, root: Path) -> None:
        """A directory inside the root works as before."""
        async with LocalFileAdapter({"path": f"{root}/data"}) as adapter:
            files = await adapter.list_files("*.csv")
        assert [f.name for f in files] == ["orders.csv"]


class TestDuckDBAdapter:
    """The DuckDB adapter checks its path every time it connects."""

    @pytest.mark.parametrize("source_type", ["directory", "database"])
    @pytest.mark.asyncio
    async def test_refuses_to_connect_outside_the_root(
        self, escaping_path: str, source_type: str
    ) -> None:
        """No connection opens for a path outside the root, in either mode."""
        adapter = DuckDBAdapter({"path": escaping_path, "source_type": source_type})
        with pytest.raises(InvalidConfigError):
            await adapter.connect()
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_refuses_a_database_file_linked_from_outside(
        self, root: Path, tmp_path: Path
    ) -> None:
        """A symlink inside the root cannot lead to a database file outside it."""
        secret = tmp_path / "outside" / "secret.duckdb"
        duckdb.connect(str(secret)).close()
        (root / "data" / "linked.duckdb").symlink_to(secret)
        adapter = DuckDBAdapter({"path": f"{root}/data/linked.duckdb", "source_type": "database"})
        with pytest.raises(InvalidConfigError):
            await adapter.connect()

    @pytest.mark.parametrize(
        "config",
        [
            {"path": "data", "source_type": "directory"},
            {"path": "data/shop.duckdb", "source_type": "database"},
            {"path": ":memory:", "source_type": "database"},
        ],
    )
    @pytest.mark.asyncio
    async def test_refuses_to_connect_while_the_root_is_unset(
        self, no_root: None, config: dict[str, str]
    ) -> None:
        """Without a root, every DuckDB source is refused, in-memory ones included."""
        adapter = DuckDBAdapter(config)
        with pytest.raises(InvalidConfigError, match=ROOT_ENV):
            await adapter.connect()

    @pytest.mark.asyncio
    async def test_queries_a_directory_inside_the_root(self, root: Path) -> None:
        """A directory inside the root is registered and queryable."""
        async with DuckDBAdapter({"path": f"{root}/data", "source_type": "directory"}) as adapter:
            result = await adapter.execute_query("SELECT count(*) AS n FROM orders")
        assert result.rows == [{"n": 2}]

    @pytest.mark.asyncio
    async def test_opens_a_database_file_inside_the_root(self, root: Path) -> None:
        """A database file inside the root opens as before."""
        db_path = root / "data" / "shop.duckdb"
        setup = duckdb.connect(str(db_path))
        setup.execute("CREATE TABLE orders AS SELECT 42 AS id")
        setup.close()
        async with DuckDBAdapter({"path": str(db_path), "source_type": "database"}) as adapter:
            result = await adapter.execute_query("SELECT id FROM orders")
        assert result.rows == [{"id": 42}]


class TestSQLiteAdapter:
    """The SQLite adapter checks its path every time it connects."""

    @pytest.mark.asyncio
    async def test_refuses_to_connect_outside_the_root(self, escaping_path: str) -> None:
        """No database opens for a path outside the root."""
        adapter = SQLiteAdapter({"path": escaping_path})
        with pytest.raises(InvalidConfigError):
            await adapter.connect()
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_refuses_a_database_file_linked_from_outside(
        self, root: Path, tmp_path: Path
    ) -> None:
        """A symlink inside the root cannot lead to a database file outside it."""
        secret = make_sqlite(tmp_path / "outside" / "secret.sqlite")
        (root / "data" / "linked.sqlite").symlink_to(secret)
        with pytest.raises(InvalidConfigError):
            await SQLiteAdapter({"path": f"{root}/data/linked.sqlite"}).connect()

    @pytest.mark.parametrize(
        "uri", ["file:/etc/hosts?mode=ro", "file:{root}/data/new.sqlite?mode=rwc"]
    )
    @pytest.mark.asyncio
    async def test_refuses_file_uris(self, root: Path, uri: str) -> None:
        """A file: URI could name any file and pick its own open mode."""
        with pytest.raises(InvalidConfigError):
            await SQLiteAdapter({"path": uri.format(root=root)}).connect()
        assert not (root / "data" / "new.sqlite").exists()

    @pytest.mark.parametrize("path", [":memory:", "data/shop.sqlite"])
    @pytest.mark.asyncio
    async def test_refuses_to_connect_while_the_root_is_unset(
        self, no_root: None, path: str
    ) -> None:
        """Without a root, SQLite sources are refused, in-memory ones included."""
        with pytest.raises(InvalidConfigError, match=ROOT_ENV):
            await SQLiteAdapter({"path": path}).connect()

    @pytest.mark.asyncio
    async def test_queries_a_database_file_inside_the_root(self, root: Path) -> None:
        """A database file inside the root opens as before."""
        db = make_sqlite(root / "data" / "shop.sqlite")
        async with SQLiteAdapter({"path": str(db)}) as adapter:
            result = await adapter.execute_query("SELECT id FROM orders")
        assert result.rows == [{"id": 42}]

    @pytest.mark.asyncio
    async def test_uri_characters_stay_part_of_the_file_name(self, root: Path) -> None:
        """A ? in the file name cannot switch files or drop read-only mode."""
        db = make_sqlite(root / "data" / "odd?name.sqlite")
        async with SQLiteAdapter({"path": str(db)}) as adapter:
            result = await adapter.execute_query("SELECT id FROM orders")
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                await adapter.execute_query("INSERT INTO orders VALUES (1)")
        assert result.rows == [{"id": 42}]
        assert not (root / "data" / "odd").exists()

    @pytest.mark.asyncio
    async def test_cannot_attach_another_database_file(self, root: Path, tmp_path: Path) -> None:
        """SQL cannot reach other database files on the host by attaching them."""
        secret = make_sqlite(tmp_path / "outside" / "secret.sqlite")
        db = make_sqlite(root / "data" / "shop.sqlite")
        async with SQLiteAdapter({"path": str(db)}) as adapter:
            with pytest.raises(sqlite3.OperationalError, match="too many attached databases"):
                await adapter.execute_query(f"ATTACH DATABASE '{secret}' AS secret")


class TestDbtManifest:
    """The dbt lineage adapter reads a local manifest only from inside the root."""

    @pytest.mark.parametrize("where", ["outside", "escaping-symlink"])
    @pytest.mark.asyncio
    async def test_refuses_a_manifest_outside_the_root(
        self, root: Path, tmp_path: Path, where: str
    ) -> None:
        """A manifest outside the root is never read, however the path gets there."""
        write_manifest(tmp_path / "outside" / "manifest.json")
        path = {
            "outside": tmp_path / "outside" / "manifest.json",
            "escaping-symlink": root / "escape" / "manifest.json",
        }[where]
        with pytest.raises(InvalidConfigError):
            await DbtAdapter({"manifest_path": str(path)}).search_datasets("orders")

    @pytest.mark.asyncio
    async def test_refuses_a_manifest_while_the_root_is_unset(
        self, tmp_path: Path, no_root: None
    ) -> None:
        """Without a root, local manifests are refused."""
        manifest = write_manifest(tmp_path / "manifest.json")
        with pytest.raises(InvalidConfigError, match=ROOT_ENV):
            await DbtAdapter({"manifest_path": str(manifest)}).search_datasets("orders")

    @pytest.mark.asyncio
    async def test_reads_a_manifest_inside_the_root(self, root: Path) -> None:
        """A manifest inside the root is read as before."""
        manifest = write_manifest(root / "data" / "manifest.json")
        datasets = await DbtAdapter({"manifest_path": str(manifest)}).search_datasets("orders")
        assert [d.name for d in datasets] == ["orders"]
