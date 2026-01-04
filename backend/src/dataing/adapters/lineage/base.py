"""Base lineage adapter with shared logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from dataing.adapters.lineage.exceptions import ColumnLineageNotSupportedError
from dataing.adapters.lineage.types import (
    ColumnLineage,
    Dataset,
    DatasetId,
    Job,
    JobRun,
    LineageCapabilities,
    LineageGraph,
    LineageProviderInfo,
)


class BaseLineageAdapter(ABC):
    """Base class for lineage adapters.

    Provides:
    - Default implementations for optional methods
    - Capability checking
    - Common utilities

    Subclasses must implement:
    - capabilities (property)
    - provider_info (property)
    - get_upstream
    - get_downstream
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the adapter with configuration.

        Args:
            config: Configuration dictionary specific to the adapter type.
        """
        self._config = config

    @property
    @abstractmethod
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities.

        Returns:
            LineageCapabilities describing what this provider supports.
        """
        ...

    @property
    @abstractmethod
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information.

        Returns:
            LineageProviderInfo with provider metadata.
        """
        ...

    @abstractmethod
    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream datasets. Must be implemented.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            List of upstream datasets.
        """
        ...

    @abstractmethod
    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream datasets. Must be implemented.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            List of downstream datasets.
        """
        ...

    # --- Default implementations ---

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Default: Return None (not found).

        Args:
            dataset_id: Dataset identifier.

        Returns:
            None by default.
        """
        return None

    async def get_lineage_graph(
        self,
        dataset_id: DatasetId,
        upstream_depth: int = 3,
        downstream_depth: int = 3,
    ) -> LineageGraph:
        """Default: Build graph by traversing upstream/downstream.

        Args:
            dataset_id: Center dataset.
            upstream_depth: Levels to traverse upstream.
            downstream_depth: Levels to traverse downstream.

        Returns:
            LineageGraph with datasets and edges.
        """
        from dataing.adapters.lineage.graph import build_graph_from_traversal

        return await build_graph_from_traversal(
            adapter=self,
            root=dataset_id,
            upstream_depth=upstream_depth,
            downstream_depth=downstream_depth,
        )

    async def get_column_lineage(
        self,
        dataset_id: DatasetId,
        column_name: str,
    ) -> list[ColumnLineage]:
        """Default: Raise not supported.

        Args:
            dataset_id: Dataset containing the column.
            column_name: Column to trace.

        Returns:
            Empty list if column lineage is supported.

        Raises:
            ColumnLineageNotSupportedError: If provider doesn't support it.
        """
        if not self.capabilities.supports_column_lineage:
            raise ColumnLineageNotSupportedError(
                f"Provider {self.provider_info.provider.value} " "does not support column lineage"
            )
        return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Default: Return None.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            None by default.
        """
        return None

    async def get_consuming_jobs(self, dataset_id: DatasetId) -> list[Job]:
        """Default: Return empty list.

        Args:
            dataset_id: Dataset to find consumers for.

        Returns:
            Empty list by default.
        """
        return []

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Default: Return empty list.

        Args:
            job_id: Job to get runs for.
            limit: Maximum runs to return.

        Returns:
            Empty list by default.
        """
        return []

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Default: Return empty list.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Empty list by default.
        """
        return []

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """Default: Return empty list.

        Args:
            platform: Filter by platform.
            database: Filter by database.
            schema: Filter by schema.
            limit: Maximum results.

        Returns:
            Empty list by default.
        """
        return []
