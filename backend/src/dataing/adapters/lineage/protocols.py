"""Lineage Adapter Protocol.

All lineage adapters implement this protocol, providing a unified
interface regardless of the underlying provider.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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


@runtime_checkable
class LineageAdapter(Protocol):
    """Protocol for lineage adapters.

    All lineage adapters must implement this interface to provide
    consistent lineage retrieval regardless of the underlying source.
    """

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities.

        Returns:
            LineageCapabilities describing what this provider supports.
        """
        ...

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information.

        Returns:
            LineageProviderInfo with provider metadata.
        """
        ...

    # --- Dataset Lineage ---

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset metadata.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset if found, None otherwise.
        """
        ...

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream datasets.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream (1 = direct parents).

        Returns:
            List of upstream datasets.
        """
        ...

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream datasets.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream (1 = direct children).

        Returns:
            List of downstream datasets.
        """
        ...

    async def get_lineage_graph(
        self,
        dataset_id: DatasetId,
        upstream_depth: int = 3,
        downstream_depth: int = 3,
    ) -> LineageGraph:
        """Get full lineage graph around a dataset.

        Args:
            dataset_id: Center dataset.
            upstream_depth: Levels to traverse upstream.
            downstream_depth: Levels to traverse downstream.

        Returns:
            LineageGraph with datasets, edges, and jobs.
        """
        ...

    # --- Column Lineage ---

    async def get_column_lineage(
        self,
        dataset_id: DatasetId,
        column_name: str,
    ) -> list[ColumnLineage]:
        """Get column-level lineage.

        Args:
            dataset_id: Dataset containing the column.
            column_name: Column to trace.

        Returns:
            List of column lineage mappings.

        Raises:
            ColumnLineageNotSupportedError: If provider doesn't support it.
        """
        ...

    # --- Job Information ---

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get the job that produces this dataset.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        ...

    async def get_consuming_jobs(self, dataset_id: DatasetId) -> list[Job]:
        """Get jobs that consume this dataset.

        Args:
            dataset_id: Dataset to find consumers for.

        Returns:
            List of consuming jobs.
        """
        ...

    async def get_recent_runs(
        self,
        job_id: str,
        limit: int = 10,
    ) -> list[JobRun]:
        """Get recent runs of a job.

        Args:
            job_id: Job to get runs for.
            limit: Maximum runs to return.

        Returns:
            List of job runs, newest first.
        """
        ...

    # --- Search ---

    async def search_datasets(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Dataset]:
        """Search for datasets by name or description.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Matching datasets.
        """
        ...

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """List datasets with optional filters.

        Args:
            platform: Filter by platform.
            database: Filter by database.
            schema: Filter by schema.
            limit: Maximum results.

        Returns:
            List of datasets.
        """
        ...
