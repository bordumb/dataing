"""OpenLineage / Marquez adapter.

OpenLineage is an open standard for lineage metadata.
Marquez is the reference implementation backend.

OpenLineage captures runtime lineage from:
- Spark jobs
- Airflow tasks
- dbt runs
- Custom integrations
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from dataing.adapters.lineage.base import BaseLineageAdapter
from dataing.adapters.lineage.registry import (
    LineageConfigField,
    LineageConfigSchema,
    register_lineage_adapter,
)
from dataing.adapters.lineage.types import (
    Dataset,
    DatasetId,
    DatasetType,
    Job,
    JobRun,
    JobType,
    LineageCapabilities,
    LineageProviderInfo,
    LineageProviderType,
    RunStatus,
)


@register_lineage_adapter(
    provider_type=LineageProviderType.OPENLINEAGE,
    display_name="OpenLineage (Marquez)",
    description="Runtime lineage from Spark, Airflow, dbt, and more",
    capabilities=LineageCapabilities(
        supports_column_lineage=True,
        supports_job_runs=True,
        supports_freshness=True,
        supports_search=True,
        supports_owners=False,
        supports_tags=True,
        is_realtime=True,
    ),
    config_schema=LineageConfigSchema(
        fields=[
            LineageConfigField(
                name="base_url",
                label="Marquez API URL",
                type="string",
                required=True,
                placeholder="http://localhost:5000",
            ),
            LineageConfigField(
                name="namespace",
                label="Default Namespace",
                type="string",
                required=True,
                default="default",
            ),
            LineageConfigField(
                name="api_key",
                label="API Key",
                type="secret",
                required=False,
            ),
        ]
    ),
)
class OpenLineageAdapter(BaseLineageAdapter):
    """OpenLineage / Marquez adapter.

    Config:
        base_url: Marquez API URL (e.g., http://localhost:5000)
        namespace: Default namespace for queries
        api_key: Optional API key for authentication
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the OpenLineage adapter.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self._base_url = config.get("base_url", "http://localhost:5000").rstrip("/")
        self._namespace = config.get("namespace", "default")

        headers: dict[str, str] = {}
        api_key = config.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v1",
            headers=headers,
        )

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        return LineageCapabilities(
            supports_column_lineage=True,
            supports_job_runs=True,
            supports_freshness=True,
            supports_search=True,
            supports_owners=False,
            supports_tags=True,
            is_realtime=True,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
        return LineageProviderInfo(
            provider=LineageProviderType.OPENLINEAGE,
            display_name="OpenLineage (Marquez)",
            description="Runtime lineage from Spark, Airflow, dbt, and more",
            capabilities=self.capabilities,
        )

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset from Marquez.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset if found, None otherwise.
        """
        try:
            response = await self._client.get(
                f"/namespaces/{self._namespace}/datasets/{dataset_id.name}"
            )
            response.raise_for_status()
            data = response.json()
            return self._api_to_dataset(data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream datasets from Marquez lineage API.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            List of upstream datasets.
        """
        try:
            response = await self._client.get(
                "/lineage",
                params={
                    "nodeId": f"dataset:{self._namespace}:{dataset_id.name}",
                    "depth": depth,
                },
            )
            response.raise_for_status()

            lineage = response.json()
            return self._extract_upstream(lineage, dataset_id)
        except httpx.HTTPError:
            return []

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream datasets from Marquez lineage API.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            List of downstream datasets.
        """
        try:
            response = await self._client.get(
                "/lineage",
                params={
                    "nodeId": f"dataset:{self._namespace}:{dataset_id.name}",
                    "depth": depth,
                },
            )
            response.raise_for_status()

            lineage = response.json()
            return self._extract_downstream(lineage, dataset_id)
        except httpx.HTTPError:
            return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get job that produces this dataset.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        dataset = await self.get_dataset(dataset_id)
        if not dataset or not dataset.extra.get("produced_by"):
            return None

        job_name = dataset.extra["produced_by"]
        try:
            response = await self._client.get(f"/namespaces/{self._namespace}/jobs/{job_name}")
            response.raise_for_status()
            return self._api_to_job(response.json())
        except httpx.HTTPError:
            return None

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Get recent runs of a job.

        Args:
            job_id: Job to get runs for.
            limit: Maximum runs to return.

        Returns:
            List of job runs, newest first.
        """
        try:
            response = await self._client.get(
                f"/namespaces/{self._namespace}/jobs/{job_id}/runs",
                params={"limit": limit},
            )
            response.raise_for_status()

            runs = response.json().get("runs", [])
            return [self._api_to_run(r) for r in runs]
        except httpx.HTTPError:
            return []

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search datasets in Marquez.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Matching datasets.
        """
        try:
            response = await self._client.get(
                "/search",
                params={"q": query, "filter": "dataset", "limit": limit},
            )
            response.raise_for_status()

            results = response.json().get("results", [])
            return [self._api_to_dataset(r) for r in results]
        except httpx.HTTPError:
            return []

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """List datasets in namespace.

        Args:
            platform: Filter by platform (not used - Marquez doesn't support).
            database: Filter by database (not used).
            schema: Filter by schema (not used).
            limit: Maximum results.

        Returns:
            List of datasets.
        """
        try:
            response = await self._client.get(
                f"/namespaces/{self._namespace}/datasets",
                params={"limit": limit},
            )
            response.raise_for_status()

            datasets = response.json().get("datasets", [])
            return [self._api_to_dataset(d) for d in datasets]
        except httpx.HTTPError:
            return []

    # --- Helper methods ---

    def _api_to_dataset(self, data: dict[str, Any]) -> Dataset:
        """Convert Marquez API response to Dataset.

        Args:
            data: Marquez dataset response.

        Returns:
            Dataset instance.
        """
        name = data.get("name", "")
        parts = name.split(".")

        return Dataset(
            id=DatasetId(
                platform=data.get("sourceName", "unknown"),
                name=name,
            ),
            name=parts[-1] if parts else name,
            qualified_name=name,
            dataset_type=DatasetType.TABLE,
            platform=data.get("sourceName", "unknown"),
            database=parts[0] if len(parts) > 2 else None,
            schema=parts[1] if len(parts) > 2 else (parts[0] if len(parts) > 1 else None),
            description=data.get("description"),
            tags=[t.get("name", "") for t in data.get("tags", [])],
            last_modified=self._parse_datetime(data.get("updatedAt")),
            extra={
                "produced_by": (data.get("currentVersion", {}).get("run", {}).get("jobName")),
            },
        )

    def _api_to_job(self, data: dict[str, Any]) -> Job:
        """Convert Marquez job response to Job.

        Args:
            data: Marquez job response.

        Returns:
            Job instance.
        """
        return Job(
            id=data.get("name", ""),
            name=data.get("name", ""),
            job_type=JobType.UNKNOWN,
            inputs=[
                DatasetId(platform="unknown", name=i.get("name", ""))
                for i in data.get("inputs", [])
            ],
            outputs=[
                DatasetId(platform="unknown", name=o.get("name", ""))
                for o in data.get("outputs", [])
            ],
            source_code_url=(data.get("facets", {}).get("sourceCodeLocation", {}).get("url")),
        )

    def _api_to_run(self, data: dict[str, Any]) -> JobRun:
        """Convert Marquez run response to JobRun.

        Args:
            data: Marquez run response.

        Returns:
            JobRun instance.
        """
        state = data.get("state", "").upper()
        status_map: dict[str, RunStatus] = {
            "RUNNING": RunStatus.RUNNING,
            "COMPLETED": RunStatus.SUCCESS,
            "FAILED": RunStatus.FAILED,
            "ABORTED": RunStatus.CANCELLED,
        }

        started_at = self._parse_datetime(data.get("startedAt"))
        ended_at = self._parse_datetime(data.get("endedAt"))

        duration_ms = data.get("durationMs")
        duration_seconds = duration_ms / 1000 if duration_ms else None

        return JobRun(
            id=data.get("id", ""),
            job_id=data.get("jobName", ""),
            status=status_map.get(state, RunStatus.FAILED),
            started_at=started_at or datetime.now(),
            ended_at=ended_at,
            duration_seconds=duration_seconds,
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse ISO datetime string.

        Args:
            value: ISO datetime string.

        Returns:
            Parsed datetime or None.
        """
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _extract_upstream(self, lineage: dict[str, Any], dataset_id: DatasetId) -> list[Dataset]:
        """Extract upstream datasets from lineage graph.

        Args:
            lineage: Marquez lineage response.
            dataset_id: Target dataset.

        Returns:
            List of upstream datasets.
        """
        # Marquez returns a graph structure with nodes and edges
        # Find all nodes that are upstream of the target
        graph = lineage.get("graph", [])
        target_key = f"dataset:{self._namespace}:{dataset_id.name}"

        # Build adjacency list for reverse traversal
        edges_to: dict[str, list[str]] = {}
        nodes: dict[str, dict[str, Any]] = {}

        for node in graph:
            node_id = node.get("id", "")
            nodes[node_id] = node
            for edge in node.get("inEdges", []):
                origin = edge.get("origin", "")
                edges_to.setdefault(node_id, []).append(origin)

        # BFS to find upstream
        upstream: list[Dataset] = []
        visited: set[str] = set()
        queue = [target_key]

        while queue:
            current = queue.pop(0)
            for parent in edges_to.get(current, []):
                if parent in visited:
                    continue
                visited.add(parent)

                if parent.startswith("dataset:"):
                    node = nodes.get(parent, {})
                    data = node.get("data", {})
                    if data:
                        upstream.append(self._api_to_dataset(data))
                    queue.append(parent)

        return upstream

    def _extract_downstream(self, lineage: dict[str, Any], dataset_id: DatasetId) -> list[Dataset]:
        """Extract downstream datasets from lineage graph.

        Args:
            lineage: Marquez lineage response.
            dataset_id: Target dataset.

        Returns:
            List of downstream datasets.
        """
        graph = lineage.get("graph", [])
        target_key = f"dataset:{self._namespace}:{dataset_id.name}"

        # Build adjacency list for forward traversal
        edges_from: dict[str, list[str]] = {}
        nodes: dict[str, dict[str, Any]] = {}

        for node in graph:
            node_id = node.get("id", "")
            nodes[node_id] = node
            for edge in node.get("outEdges", []):
                destination = edge.get("destination", "")
                edges_from.setdefault(node_id, []).append(destination)

        # BFS to find downstream
        downstream: list[Dataset] = []
        visited: set[str] = set()
        queue = [target_key]

        while queue:
            current = queue.pop(0)
            for child in edges_from.get(current, []):
                if child in visited:
                    continue
                visited.add(child)

                if child.startswith("dataset:"):
                    node = nodes.get(child, {})
                    data = node.get("data", {})
                    if data:
                        downstream.append(self._api_to_dataset(data))
                    queue.append(child)

        return downstream
