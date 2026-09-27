"""Tests for schema discovery in the file system adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import duckdb
import pytest

from dataing.adapters.datasource.filesystem.base import FileInfo
from dataing.adapters.datasource.filesystem.gcs import GCSAdapter
from dataing.adapters.datasource.filesystem.hdfs import HDFSAdapter
from dataing.adapters.datasource.filesystem.local import LocalFileAdapter
from dataing.adapters.datasource.types import NormalizedType

ORDERS_COLUMNS = [("id", NormalizedType.INTEGER), ("amount", NormalizedType.INTEGER)]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A directory holding one CSV data file."""
    (tmp_path / "orders.csv").write_text("id,amount\n1,10\n")
    return tmp_path


@pytest.fixture
async def local_adapter(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[LocalFileAdapter]:
    """A connected local file adapter over data_dir."""
    monkeypatch.setenv("DATAING_LOCAL_DATA_ROOT", str(data_dir))
    adapter = LocalFileAdapter({"path": str(data_dir)})
    await adapter.connect()
    yield adapter
    await adapter.disconnect()


@pytest.fixture(
    params=[
        pytest.param((GCSAdapter, {"bucket": "warehouse"}), id="gcs"),
        pytest.param((HDFSAdapter, {"namenode_host": "namenode", "path": "/warehouse"}), id="hdfs"),
    ]
)
async def remote_adapter(
    request: pytest.FixtureRequest, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[GCSAdapter | HDFSAdapter]:
    """A GCS or HDFS adapter whose file listing is served from data_dir.

    connect() would load DuckDB's httpfs extension over the network, so the
    adapter gets a plain in-memory connection that reads the listed local files.
    """
    adapter_cls, config = request.param
    adapter = adapter_cls(config)

    async def list_files(pattern: str = "*", recursive: bool = True) -> list[FileInfo]:
        return [
            FileInfo(path=str(path), name=path.name, size_bytes=path.stat().st_size)
            for path in sorted(data_dir.glob(pattern))
        ]

    monkeypatch.setattr(adapter, "list_files", list_files)
    adapter._conn = duckdb.connect(":memory:")
    adapter._connected = True
    yield adapter
    await adapter.disconnect()


class TestLocalFileAdapterGetSchema:
    """LocalFileAdapter lists each data file in its directory as a table."""

    async def test_file_becomes_a_table_with_its_columns(
        self, local_adapter: LocalFileAdapter, data_dir: Path
    ) -> None:
        """A CSV file in the directory is returned as a table with its columns."""
        schema = await local_adapter.get_schema()

        [table] = schema.get_all_tables()
        assert table.name == "orders"
        assert table.native_path == str(data_dir / "orders.csv")
        assert [(c.name, c.data_type) for c in table.columns] == ORDERS_COLUMNS

    async def test_unreadable_file_is_listed_without_columns(
        self, local_adapter: LocalFileAdapter, data_dir: Path
    ) -> None:
        """A file DuckDB cannot read is still listed, just without columns."""
        (data_dir / "corrupt.parquet").write_bytes(b"not parquet")

        schema = await local_adapter.get_schema()

        tables = {t.name: t for t in schema.get_all_tables()}
        assert tables["corrupt"].columns == []
        assert [(c.name, c.data_type) for c in tables["orders"].columns] == ORDERS_COLUMNS


class TestRemoteFileAdapterGetSchema:
    """GCS and HDFS turn each listed file into a table the same way."""

    async def test_listed_file_becomes_a_table_with_its_columns(
        self, remote_adapter: GCSAdapter | HDFSAdapter
    ) -> None:
        """A CSV file in the listing is returned as a table with its columns."""
        schema = await remote_adapter.get_schema()

        [table] = schema.get_all_tables()
        assert table.name == "orders"
        assert [(c.name, c.data_type) for c in table.columns] == ORDERS_COLUMNS
