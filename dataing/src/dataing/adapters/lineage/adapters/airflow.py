"""Airflow lineage adapter.

Gets lineage from Airflow's metadata database or REST API.
Airflow 2.x has lineage support via inlets/outlets on operators.
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
    provider_type=LineageProviderType.AIRFLOW,
    display_name="Apache Airflow",
    description="Lineage from Airflow DAGs (inlets/outlets)",
    capabilities=LineageCapabilities(
        supports_column_lineage=False,
        supports_job_runs=True,
        supports_freshness=True,
        supports_search=True,
        supports_owners=True,
        supports_tags=True,
        is_realtime=False,
    ),
    config_schema=LineageConfigSchema(
        fields=[
            LineageConfigField(
                name="base_url",
                label="Airflow API URL",
                type="string",
                required=True,
                placeholder="http://localhost:8080",
            ),
            LineageConfigField(
                name="username",
                label="Username",
                type="string",
                required=True,
            ),
            LineageConfigField(
                name="password",
                label="Password",
                type="secret",
                required=True,
            ),
        ]
    ),
)
class AirflowAdapter(BaseLineageAdapter):
    """Airflow lineage adapter.

    Config:
        base_url: Airflow REST API URL
        username: Airflow username
        password: Airflow password

    Note: Requires Airflow 2.x with REST API enabled.
    Lineage quality depends on operators defining inlets/outlets.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the Airflow adapter.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self._base_url = config.get("base_url", "").rstrip("/")
        username = config.get("username", "")
        password = config.get("password", "")

        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v1",
            auth=(username, password),
        )

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        return LineageCapabilities(
            supports_column_lineage=False,
            supports_job_runs=True,
            supports_freshness=True,
            supports_search=True,
            supports_owners=True,
            supports_tags=True,
            is_realtime=False,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
        return LineageProviderInfo(
            provider=LineageProviderType.AIRFLOW,
            display_name="Apache Airflow",
            description="Lineage from Airflow DAGs (inlets/outlets)",
            capabilities=self.capabilities,
        )

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream from Airflow's dataset dependencies.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            List of upstream datasets.
        """
        # Airflow 2.4+ has Datasets feature
        # Query /datasets/{uri}/events to find producing tasks
        try:
            # Get dataset info
            dataset_uri = dataset_id.name
            response = await self._client.get(f"/datasets/{dataset_uri}")
            if not response.is_success:
                return []

            data = response.json()
            producing_tasks = data.get("producing_tasks", [])

            upstream: list[Dataset] = []
            visited: set[str] = set()

            for task_info in producing_tasks:
                dag_id = task_info.get("dag_id", "")
                task_id = task_info.get("task_id", "")

                if dag_id in visited:
                    continue
                visited.add(dag_id)

                # Get task's inlets (upstream datasets)
                task_response = await self._client.get(f"/dags/{dag_id}/tasks/{task_id}")
                if task_response.is_success:
                    task_data = task_response.json()
                    for inlet in task_data.get("inlets", []):
                        inlet_uri = inlet.get("uri", "")
                        if inlet_uri:
                            upstream.append(
                                Dataset(
                                    id=DatasetId(platform="airflow", name=inlet_uri),
                                    name=inlet_uri.split("/")[-1],
                                    qualified_name=inlet_uri,
                                    dataset_type=DatasetType.TABLE,
                                    platform="airflow",
                                )
                            )

            return upstream
        except httpx.HTTPError:
            return []

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream from Airflow's dataset dependencies.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            List of downstream datasets.
        """
        try:
            dataset_uri = dataset_id.name
            response = await self._client.get(f"/datasets/{dataset_uri}")
            if not response.is_success:
                return []

            data = response.json()
            consuming_dags = data.get("consuming_dags", [])

            downstream: list[Dataset] = []
            visited: set[str] = set()

            for dag_info in consuming_dags:
                dag_id = dag_info.get("dag_id", "")

                if dag_id in visited:
                    continue
                visited.add(dag_id)

                # Get DAG's outlets
                dag_response = await self._client.get(f"/dags/{dag_id}/tasks")
                if dag_response.is_success:
                    tasks = dag_response.json().get("tasks", [])
                    for task in tasks:
                        for outlet in task.get("outlets", []):
                            outlet_uri = outlet.get("uri", "")
                            if outlet_uri and outlet_uri != dataset_uri:
                                downstream.append(
                                    Dataset(
                                        id=DatasetId(platform="airflow", name=outlet_uri),
                                        name=outlet_uri.split("/")[-1],
                                        qualified_name=outlet_uri,
                                        dataset_type=DatasetType.TABLE,
                                        platform="airflow",
                                    )
                                )

            return downstream
        except httpx.HTTPError:
            return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Find task that produces this dataset.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        try:
            dataset_uri = dataset_id.name
            response = await self._client.get(f"/datasets/{dataset_uri}")
            if not response.is_success:
                return None

            data = response.json()
            producing_tasks = data.get("producing_tasks", [])

            if not producing_tasks:
                return None

            task_info = producing_tasks[0]
            dag_id = task_info.get("dag_id", "")
            task_id = task_info.get("task_id", "")

            # Get task details
            task_response = await self._client.get(f"/dags/{dag_id}/tasks/{task_id}")
            if not task_response.is_success:
                return None

            task_data = task_response.json()

            return Job(
                id=f"{dag_id}/{task_id}",
                name=f"{dag_id}.{task_id}",
                job_type=JobType.AIRFLOW_TASK,
                inputs=[
                    DatasetId(platform="airflow", name=inlet.get("uri", ""))
                    for inlet in task_data.get("inlets", [])
                ],
                outputs=[
                    DatasetId(platform="airflow", name=outlet.get("uri", ""))
                    for outlet in task_data.get("outlets", [])
                ],
                owners=task_data.get("owner", "").split(",") if task_data.get("owner") else [],
            )
        except httpx.HTTPError:
            return None

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Get recent DAG runs.

        Args:
            job_id: Job ID in format "dag_id/task_id" or "dag_id".
            limit: Maximum runs to return.

        Returns:
            List of job runs, newest first.
        """
        try:
            parts = job_id.split("/")
            dag_id = parts[0]

            response = await self._client.get(
                f"/dags/{dag_id}/dagRuns",
                params={"limit": limit, "order_by": "-execution_date"},
            )
            response.raise_for_status()

            runs = response.json().get("dag_runs", [])
            return [self._api_to_run(r, dag_id) for r in runs]
        except httpx.HTTPError:
            return []

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search for datasets by URI.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Matching datasets.
        """
        try:
            response = await self._client.get(
                "/datasets",
                params={"limit": limit, "uri_pattern": f"%{query}%"},
            )
            response.raise_for_status()

            datasets = response.json().get("datasets", [])
            return [self._api_to_dataset(d) for d in datasets]
        except httpx.HTTPError:
            return []

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """List all registered datasets.

        Args:
            platform: Filter by platform (not used).
            database: Filter by database (not used).
            schema: Filter by schema (not used).
            limit: Maximum results.

        Returns:
            List of datasets.
        """
        try:
            response = await self._client.get(
                "/datasets",
                params={"limit": limit},
            )
            response.raise_for_status()

            datasets = response.json().get("datasets", [])
            return [self._api_to_dataset(d) for d in datasets]
        except httpx.HTTPError:
            return []

    # --- Helper methods ---

    def _api_to_dataset(self, data: dict[str, Any]) -> Dataset:
        """Convert Airflow dataset response to Dataset.

        Args:
            data: Airflow dataset response.

        Returns:
            Dataset instance.
        """
        uri = data.get("uri", "")
        return Dataset(
            id=DatasetId(platform="airflow", name=uri),
            name=uri.split("/")[-1] if "/" in uri else uri,
            qualified_name=uri,
            dataset_type=DatasetType.TABLE,
            platform="airflow",
            description=data.get("extra", {}).get("description"),
            last_modified=self._parse_datetime(data.get("updated_at")),
        )

    def _api_to_run(self, data: dict[str, Any], dag_id: str) -> JobRun:
        """Convert Airflow DAG run response to JobRun.

        Args:
            data: Airflow DAG run response.
            dag_id: The DAG ID.

        Returns:
            JobRun instance.
        """
        state = data.get("state", "").lower()
        status_map: dict[str, RunStatus] = {
            "running": RunStatus.RUNNING,
            "success": RunStatus.SUCCESS,
            "failed": RunStatus.FAILED,
            "queued": RunStatus.RUNNING,
            "skipped": RunStatus.SKIPPED,
        }

        started_at = self._parse_datetime(data.get("start_date"))
        ended_at = self._parse_datetime(data.get("end_date"))

        duration_seconds = None
        if started_at and ended_at:
            duration_seconds = (ended_at - started_at).total_seconds()

        return JobRun(
            id=data.get("dag_run_id", ""),
            job_id=dag_id,
            status=status_map.get(state, RunStatus.FAILED),
            started_at=started_at or datetime.now(),
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            logs_url=data.get("external_trigger"),
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
