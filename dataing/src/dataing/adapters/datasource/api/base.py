"""Base class for API adapters.

This module provides the abstract base class for all API-based
data source adapters.
"""

from __future__ import annotations

from abc import abstractmethod

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    QueryLanguage,
    QueryResult,
    Table,
)


class APIAdapter(BaseAdapter):
    """Abstract base class for API adapters.

    Extends BaseAdapter with API-specific query capabilities.
    """

    @property
    def capabilities(self) -> AdapterCapabilities:
        """API adapters typically have rate limits."""
        return AdapterCapabilities(
            supports_sql=False,
            supports_sampling=True,
            supports_row_count=True,
            supports_column_stats=False,
            supports_preview=True,
            supports_write=False,
            rate_limit_requests_per_minute=100,
            max_concurrent_queries=1,
            query_language=QueryLanguage.SCAN_ONLY,
        )

    @abstractmethod
    async def query_object(
        self,
        object_name: str,
        query: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Query an API object/entity.

        Args:
            object_name: Name of the object to query.
            query: Optional query string (e.g., SOQL for Salesforce).
            limit: Maximum records to return.

        Returns:
            QueryResult with records.
        """
        ...

    @abstractmethod
    async def describe_object(
        self,
        object_name: str,
    ) -> Table:
        """Get the schema of an API object.

        Args:
            object_name: Name of the object.

        Returns:
            Table with field definitions.
        """
        ...

    @abstractmethod
    async def list_objects(self) -> list[str]:
        """List all available objects in the API.

        Returns:
            List of object names.
        """
        ...

    async def preview(
        self,
        object_name: str,
        n: int = 100,
    ) -> QueryResult:
        """Get a preview of records from an object.

        Args:
            object_name: Object name.
            n: Number of records to preview.

        Returns:
            QueryResult with preview records.
        """
        return await self.query_object(object_name, limit=n)

    async def sample(
        self,
        object_name: str,
        n: int = 100,
    ) -> QueryResult:
        """Get a sample of records from an object.

        Most APIs don't support true random sampling, so this
        defaults to returning the first N records.

        Args:
            object_name: Object name.
            n: Number of records to sample.

        Returns:
            QueryResult with sampled records.
        """
        return await self.query_object(object_name, limit=n)
