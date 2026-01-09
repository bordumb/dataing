"""Base class for document/NoSQL database adapters.

This module provides the abstract base class for all document-oriented
data source adapters, adding scan and aggregation capabilities.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    QueryLanguage,
    QueryResult,
)


class DocumentAdapter(BaseAdapter):
    """Abstract base class for document/NoSQL database adapters.

    Extends BaseAdapter with document scanning and aggregation capabilities.
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Document adapters typically don't support SQL."""
        return AdapterCapabilities(
            supports_sql=False,
            supports_sampling=True,
            supports_row_count=True,
            supports_column_stats=False,
            supports_preview=True,
            supports_write=False,
            query_language=QueryLanguage.SCAN_ONLY,
            max_concurrent_queries=5,
        )

    @abstractmethod
    async def scan_collection(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> QueryResult:
        """Scan documents from a collection.

        Args:
            collection: Collection/table name.
            filter: Optional filter criteria.
            limit: Maximum documents to return.
            skip: Number of documents to skip.

        Returns:
            QueryResult with scanned documents.
        """
        ...

    @abstractmethod
    async def sample(
        self,
        collection: str,
        n: int = 100,
    ) -> QueryResult:
        """Get a random sample of documents from a collection.

        Args:
            collection: Collection name.
            n: Number of documents to sample.

        Returns:
            QueryResult with sampled documents.
        """
        ...

    @abstractmethod
    async def count_documents(
        self,
        collection: str,
        filter: dict[str, Any] | None = None,
    ) -> int:
        """Count documents in a collection.

        Args:
            collection: Collection name.
            filter: Optional filter criteria.

        Returns:
            Number of matching documents.
        """
        ...

    async def preview(
        self,
        collection: str,
        n: int = 100,
    ) -> QueryResult:
        """Get a preview of documents from a collection.

        Args:
            collection: Collection name.
            n: Number of documents to preview.

        Returns:
            QueryResult with preview documents.
        """
        return await self.scan_collection(collection, limit=n)

    @abstractmethod
    async def aggregate(
        self,
        collection: str,
        pipeline: list[dict[str, Any]],
    ) -> QueryResult:
        """Execute an aggregation pipeline.

        Args:
            collection: Collection name.
            pipeline: Aggregation pipeline stages.

        Returns:
            QueryResult with aggregation results.
        """
        ...

    @abstractmethod
    async def infer_schema(
        self,
        collection: str,
        sample_size: int = 100,
    ) -> dict[str, Any]:
        """Infer schema from document samples.

        Args:
            collection: Collection name.
            sample_size: Number of documents to sample for inference.

        Returns:
            Dictionary describing inferred schema.
        """
        ...
