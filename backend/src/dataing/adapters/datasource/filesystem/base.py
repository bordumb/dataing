"""Base class for file system adapters.

This module provides the abstract base class for all file system
data source adapters.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    QueryLanguage,
    QueryResult,
    Table,
)


@dataclass
class FileInfo:
    """Information about a file."""

    path: str
    name: str
    size_bytes: int
    last_modified: str | None = None
    file_format: str | None = None


class FileSystemAdapter(BaseAdapter):
    """Abstract base class for file system adapters.

    Extends BaseAdapter with file listing and reading capabilities.
    File system adapters typically delegate actual reading to DuckDB.
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        """File system adapters support SQL via DuckDB."""
        return AdapterCapabilities(
            supports_sql=True,
            supports_sampling=True,
            supports_row_count=True,
            supports_column_stats=True,
            supports_preview=True,
            supports_write=False,
            query_language=QueryLanguage.SQL,
            max_concurrent_queries=5,
        )

    @abstractmethod
    async def list_files(
        self,
        pattern: str = "*",
        recursive: bool = True,
    ) -> list[FileInfo]:
        """List files matching a pattern.

        Args:
            pattern: Glob pattern to match files.
            recursive: Whether to search recursively.

        Returns:
            List of FileInfo objects.
        """
        ...

    @abstractmethod
    async def read_file(
        self,
        path: str,
        file_format: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Read a file and return as QueryResult.

        Args:
            path: Path to the file.
            file_format: Format (parquet, csv, json). Auto-detected if None.
            limit: Maximum rows to return.

        Returns:
            QueryResult with file contents.
        """
        ...

    @abstractmethod
    async def infer_schema(
        self,
        path: str,
        file_format: str | None = None,
    ) -> Table:
        """Infer schema from a file.

        Args:
            path: Path to the file.
            file_format: Format (parquet, csv, json). Auto-detected if None.

        Returns:
            Table with column definitions.
        """
        ...

    async def preview(
        self,
        path: str,
        n: int = 100,
    ) -> QueryResult:
        """Get a preview of a file.

        Args:
            path: Path to the file.
            n: Number of rows to preview.

        Returns:
            QueryResult with preview data.
        """
        return await self.read_file(path, limit=n)

    async def sample(
        self,
        path: str,
        n: int = 100,
    ) -> QueryResult:
        """Get a sample from a file.

        For most file formats, sampling is equivalent to preview
        unless the underlying system supports random sampling.

        Args:
            path: Path to the file.
            n: Number of rows to sample.

        Returns:
            QueryResult with sampled data.
        """
        return await self.read_file(path, limit=n)
