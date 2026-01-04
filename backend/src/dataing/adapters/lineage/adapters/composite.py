"""Composite lineage adapter.

Merges lineage from multiple sources.
Example: dbt for model lineage + Airflow for orchestration lineage.
"""

from __future__ import annotations

import logging
from typing import Any

from dataing.adapters.lineage.base import BaseLineageAdapter
from dataing.adapters.lineage.graph import merge_graphs
from dataing.adapters.lineage.types import (
    ColumnLineage,
    Dataset,
    DatasetId,
    Job,
    JobRun,
    LineageCapabilities,
    LineageGraph,
    LineageProviderInfo,
    LineageProviderType,
)

logger = logging.getLogger(__name__)


class CompositeLineageAdapter(BaseLineageAdapter):
    """Merges lineage from multiple adapters.

    Config:
        adapters: List of (adapter, priority) tuples

    Higher priority adapters' data takes precedence in conflicts.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the Composite adapter.

        Args:
            config: Configuration dictionary with "adapters" key containing
                    list of (adapter, priority) tuples.
        """
        super().__init__(config)
        adapters_config = config.get("adapters", [])

        # Sort by priority (highest first)
        self._adapters: list[tuple[BaseLineageAdapter, int]] = sorted(
            adapters_config, key=lambda x: x[1], reverse=True
        )

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get union of all adapter capabilities."""
        if not self._adapters:
            return LineageCapabilities()

        return LineageCapabilities(
            supports_column_lineage=any(
                a.capabilities.supports_column_lineage for a, _ in self._adapters
            ),
            supports_job_runs=any(a.capabilities.supports_job_runs for a, _ in self._adapters),
            supports_freshness=any(a.capabilities.supports_freshness for a, _ in self._adapters),
            supports_search=any(a.capabilities.supports_search for a, _ in self._adapters),
            supports_owners=any(a.capabilities.supports_owners for a, _ in self._adapters),
            supports_tags=any(a.capabilities.supports_tags for a, _ in self._adapters),
            is_realtime=any(a.capabilities.is_realtime for a, _ in self._adapters),
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
        providers = [a.provider_info.provider.value for a, _ in self._adapters]
        return LineageProviderInfo(
            provider=LineageProviderType.COMPOSITE,
            display_name=f"Composite ({', '.join(providers)})",
            description="Merged lineage from multiple sources",
            capabilities=self.capabilities,
        )

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset from first adapter that has it.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset if found, None otherwise.
        """
        for adapter, _ in self._adapters:
            try:
                result = await adapter.get_dataset(dataset_id)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue
        return None

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Merge upstream from all adapters.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            Merged list of upstream datasets.
        """
        all_upstream: dict[str, Dataset] = {}

        for adapter, _ in self._adapters:
            try:
                upstream = await adapter.get_upstream(dataset_id, depth)
                for ds in upstream:
                    # First adapter wins (highest priority)
                    if str(ds.id) not in all_upstream:
                        all_upstream[str(ds.id)] = ds
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue

        return list(all_upstream.values())

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Merge downstream from all adapters.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            Merged list of downstream datasets.
        """
        all_downstream: dict[str, Dataset] = {}

        for adapter, _ in self._adapters:
            try:
                downstream = await adapter.get_downstream(dataset_id, depth)
                for ds in downstream:
                    if str(ds.id) not in all_downstream:
                        all_downstream[str(ds.id)] = ds
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue

        return list(all_downstream.values())

    async def get_lineage_graph(
        self,
        dataset_id: DatasetId,
        upstream_depth: int = 3,
        downstream_depth: int = 3,
    ) -> LineageGraph:
        """Get merged lineage graph from all adapters.

        Args:
            dataset_id: Center dataset.
            upstream_depth: Levels to traverse upstream.
            downstream_depth: Levels to traverse downstream.

        Returns:
            Merged LineageGraph.
        """
        graphs: list[LineageGraph] = []

        for adapter, _ in self._adapters:
            try:
                graph = await adapter.get_lineage_graph(
                    dataset_id, upstream_depth, downstream_depth
                )
                graphs.append(graph)
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue

        if not graphs:
            return LineageGraph(root=dataset_id)

        return merge_graphs(graphs)

    async def get_column_lineage(
        self,
        dataset_id: DatasetId,
        column_name: str,
    ) -> list[ColumnLineage]:
        """Get column lineage from first supporting adapter.

        Args:
            dataset_id: Dataset containing the column.
            column_name: Column to trace.

        Returns:
            List of column lineage mappings.
        """
        for adapter, _ in self._adapters:
            if not adapter.capabilities.supports_column_lineage:
                continue
            try:
                col_lineage = await adapter.get_column_lineage(dataset_id, column_name)
                if col_lineage:
                    result: list[ColumnLineage] = col_lineage
                    return result
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue
        empty_result: list[ColumnLineage] = []
        return empty_result

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get producing job from first adapter that has it.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        for adapter, _ in self._adapters:
            try:
                job = await adapter.get_producing_job(dataset_id)
                if job:
                    return job
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue
        return None

    async def get_consuming_jobs(self, dataset_id: DatasetId) -> list[Job]:
        """Merge consuming jobs from all adapters.

        Args:
            dataset_id: Dataset to find consumers for.

        Returns:
            Merged list of consuming jobs.
        """
        all_jobs: dict[str, Job] = {}

        for adapter, _ in self._adapters:
            try:
                jobs = await adapter.get_consuming_jobs(dataset_id)
                for job in jobs:
                    if job.id not in all_jobs:
                        all_jobs[job.id] = job
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue

        return list(all_jobs.values())

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Get runs from adapter that knows about this job.

        Args:
            job_id: Job to get runs for.
            limit: Maximum runs to return.

        Returns:
            List of job runs.
        """
        for adapter, _ in self._adapters:
            try:
                runs = await adapter.get_recent_runs(job_id, limit)
                if runs:
                    result: list[JobRun] = runs
                    return result
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue
        empty_result: list[JobRun] = []
        return empty_result

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search across all adapters and merge results.

        Args:
            query: Search query.
            limit: Maximum total results.

        Returns:
            Merged search results.
        """
        all_datasets: dict[str, Dataset] = {}
        per_adapter_limit = max(limit // len(self._adapters), 5) if self._adapters else limit

        for adapter, _ in self._adapters:
            try:
                results = await adapter.search_datasets(query, per_adapter_limit)
                for ds in results:
                    if str(ds.id) not in all_datasets:
                        all_datasets[str(ds.id)] = ds
                        if len(all_datasets) >= limit:
                            result: list[Dataset] = list(all_datasets.values())
                            return result
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue

        final_result: list[Dataset] = list(all_datasets.values())
        return final_result

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """List datasets from all adapters.

        Args:
            platform: Filter by platform.
            database: Filter by database.
            schema: Filter by schema.
            limit: Maximum total results.

        Returns:
            Merged list of datasets.
        """
        all_datasets: dict[str, Dataset] = {}
        per_adapter_limit = max(limit // len(self._adapters), 10) if self._adapters else limit

        for adapter, _ in self._adapters:
            try:
                results = await adapter.list_datasets(platform, database, schema, per_adapter_limit)
                for ds in results:
                    if str(ds.id) not in all_datasets:
                        all_datasets[str(ds.id)] = ds
                        if len(all_datasets) >= limit:
                            result: list[Dataset] = list(all_datasets.values())
                            return result
            except Exception as e:
                logger.debug(f"Adapter {adapter.provider_info.provider} failed: {e}")
                continue

        final_result: list[Dataset] = list(all_datasets.values())
        return final_result
