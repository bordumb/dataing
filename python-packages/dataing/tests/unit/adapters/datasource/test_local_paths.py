"""Tests for keeping local data sources inside the operator's local data root."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from dataing.adapters.datasource import DuckDBAdapter, LocalFileAdapter
from dataing.adapters.datasource.errors import InvalidConfigError
from dataing.adapters.datasource.local_paths import resolve_local_path

ROOT_ENV = "DATAING_LOCAL_DATA_ROOT"


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
