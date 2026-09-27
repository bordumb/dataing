"""Tests for the local file adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import duckdb
import pytest

from dataing.adapters.datasource.filesystem.local import LocalFileAdapter


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory holding the source's files, with a file outside it.

    The operator's local data root is tmp_path, so the file outside the source is
    still inside the root: only the DuckDB sandbox keeps queries away from it.
    """
    monkeypatch.setenv("DATAING_LOCAL_DATA_ROOT", str(tmp_path))
    src = tmp_path / "data"
    src.mkdir()
    (src / "orders.csv").write_text("id,amount\n1,10\n2,20\n")
    (tmp_path / "outside.csv").write_text("secret\nleaked\n")
    return src


@pytest.fixture
async def adapter(data_dir: Path) -> AsyncIterator[LocalFileAdapter]:
    """A connected adapter over data_dir."""
    local = LocalFileAdapter({"path": str(data_dir)})
    await local.connect()
    yield local
    await local.disconnect()


class TestLocalFileAccess:
    """Queries run over the source's own files and cannot reach other host files."""

    async def test_query_over_own_files_runs(
        self, adapter: LocalFileAdapter, data_dir: Path
    ) -> None:
        """A normal investigation query over the source's file returns its rows."""
        result = await adapter.execute_query(
            f"SELECT id, amount FROM read_csv('{data_dir}/orders.csv') ORDER BY id LIMIT 10"
        )
        assert result.rows == [{"id": 1, "amount": 10}, {"id": 2, "amount": 20}]

    async def test_schema_inference_and_preview_read_own_files(
        self, adapter: LocalFileAdapter, data_dir: Path
    ) -> None:
        """Schema inference and previews keep working inside the sandbox."""
        table = await adapter.infer_schema(f"{data_dir}/orders.csv")
        assert [c.name for c in table.columns] == ["id", "amount"]

        preview = await adapter.read_file(f"{data_dir}/orders.csv", limit=1)
        assert preview.rows == [{"id": 1, "amount": 10}]

    async def test_query_cannot_read_etc_passwd(self, adapter: LocalFileAdapter) -> None:
        """The /etc/passwd read that passes SQL validation is refused by DuckDB."""
        with pytest.raises(duckdb.PermissionException):
            await adapter.execute_query("SELECT * FROM read_csv('/etc/passwd') LIMIT 10")

    async def test_query_cannot_traverse_out_of_the_directory(
        self, adapter: LocalFileAdapter, data_dir: Path
    ) -> None:
        """A path that starts inside the source but resolves outside it is refused."""
        with pytest.raises(duckdb.PermissionException):
            await adapter.execute_query(
                f"SELECT * FROM read_text('{data_dir}/./../outside.csv') LIMIT 10"
            )

    async def test_read_file_cannot_leave_the_directory(self, adapter: LocalFileAdapter) -> None:
        """read_file takes a path argument, so it is confined too."""
        with pytest.raises(duckdb.PermissionException):
            await adapter.read_file("/etc/passwd", format="csv")
