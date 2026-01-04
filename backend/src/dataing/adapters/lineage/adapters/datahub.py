"""DataHub lineage adapter.

DataHub is a metadata platform with rich lineage support.
Uses GraphQL API for queries.
"""

from __future__ import annotations

from typing import Any

import httpx

from dataing.adapters.lineage.base import BaseLineageAdapter
from dataing.adapters.lineage.registry import (
    LineageConfigField,
    LineageConfigSchema,
    register_lineage_adapter,
)
from dataing.adapters.lineage.types import (
    ColumnLineage,
    Dataset,
    DatasetId,
    DatasetType,
    Job,
    JobType,
    LineageCapabilities,
    LineageProviderInfo,
    LineageProviderType,
)


@register_lineage_adapter(
    provider_type=LineageProviderType.DATAHUB,
    display_name="DataHub",
    description="Lineage from DataHub metadata platform",
    capabilities=LineageCapabilities(
        supports_column_lineage=True,
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
                label="DataHub GMS URL",
                type="string",
                required=True,
                placeholder="http://localhost:8080",
            ),
            LineageConfigField(
                name="token",
                label="Access Token",
                type="secret",
                required=True,
            ),
        ]
    ),
)
class DataHubAdapter(BaseLineageAdapter):
    """DataHub lineage adapter.

    Config:
        base_url: DataHub GMS URL
        token: DataHub access token
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the DataHub adapter.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self._base_url = config.get("base_url", "").rstrip("/")
        token = config.get("token", "")

        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/graphql",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        return LineageCapabilities(
            supports_column_lineage=True,
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
            provider=LineageProviderType.DATAHUB,
            display_name="DataHub",
            description="Lineage from DataHub metadata platform",
            capabilities=self.capabilities,
        )

    async def _execute_graphql(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query.

        Args:
            query: GraphQL query string.
            variables: Query variables.

        Returns:
            Response data.

        Raises:
            httpx.HTTPError: If request fails.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await self._client.post("", json=payload)
        response.raise_for_status()

        result = response.json()
        if "errors" in result:
            raise httpx.HTTPStatusError(
                str(result["errors"]),
                request=response.request,
                response=response,
            )

        data: dict[str, Any] = result.get("data", {})
        return data

    def _to_datahub_urn(self, dataset_id: DatasetId) -> str:
        """Convert DatasetId to DataHub URN format.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            DataHub URN string.
        """
        return (
            f"urn:li:dataset:(urn:li:dataPlatform:{dataset_id.platform}," f"{dataset_id.name},PROD)"
        )

    def _from_datahub_urn(self, urn: str) -> DatasetId:
        """Parse DataHub URN to DatasetId.

        Args:
            urn: DataHub URN string.

        Returns:
            DatasetId instance.
        """
        # Format: urn:li:dataset:(urn:li:dataPlatform:platform,name,env)
        if not urn.startswith("urn:li:dataset:"):
            return DatasetId(platform="unknown", name=urn)

        inner = urn[len("urn:li:dataset:(") : -1]  # Remove prefix and trailing )
        parts = inner.split(",")

        platform = "unknown"
        if parts and "dataPlatform:" in parts[0]:
            platform = parts[0].split(":")[-1]

        name = parts[1] if len(parts) > 1 else ""

        return DatasetId(platform=platform, name=name)

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset from DataHub.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset if found, None otherwise.
        """
        query = """
        query GetDataset($urn: String!) {
            dataset(urn: $urn) {
                urn
                name
                platform { name }
                properties { description }
                ownership {
                    owners {
                        owner { ... on CorpUser { username } }
                    }
                }
                globalTags { tags { tag { name } } }
            }
        }
        """

        try:
            urn = self._to_datahub_urn(dataset_id)
            data = await self._execute_graphql(query, {"urn": urn})

            dataset_data = data.get("dataset")
            if not dataset_data:
                return None

            return self._api_to_dataset(dataset_data)
        except httpx.HTTPError:
            return None

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream via DataHub GraphQL.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            List of upstream datasets.
        """
        query = """
        query GetUpstream($urn: String!, $depth: Int!) {
            dataset(urn: $urn) {
                upstream: lineage(
                    input: {direction: UPSTREAM, start: 0, count: 100}
                ) {
                    entities {
                        entity {
                            urn
                            ... on Dataset {
                                name
                                platform { name }
                                properties { description }
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            urn = self._to_datahub_urn(dataset_id)
            data = await self._execute_graphql(query, {"urn": urn, "depth": depth})

            upstream_data = data.get("dataset", {}).get("upstream", {}).get("entities", [])

            return [
                self._api_to_dataset(e.get("entity", {})) for e in upstream_data if e.get("entity")
            ]
        except httpx.HTTPError:
            return []

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream via DataHub GraphQL.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            List of downstream datasets.
        """
        query = """
        query GetDownstream($urn: String!, $depth: Int!) {
            dataset(urn: $urn) {
                downstream: lineage(
                    input: {direction: DOWNSTREAM, start: 0, count: 100}
                ) {
                    entities {
                        entity {
                            urn
                            ... on Dataset {
                                name
                                platform { name }
                                properties { description }
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            urn = self._to_datahub_urn(dataset_id)
            data = await self._execute_graphql(query, {"urn": urn, "depth": depth})

            downstream_data = data.get("dataset", {}).get("downstream", {}).get("entities", [])

            return [
                self._api_to_dataset(e.get("entity", {}))
                for e in downstream_data
                if e.get("entity")
            ]
        except httpx.HTTPError:
            return []

    async def get_column_lineage(
        self,
        dataset_id: DatasetId,
        column_name: str,
    ) -> list[ColumnLineage]:
        """Get column-level lineage from DataHub.

        Args:
            dataset_id: Dataset containing the column.
            column_name: Column to trace.

        Returns:
            List of column lineage mappings.
        """
        query = """
        query GetColumnLineage($urn: String!) {
            dataset(urn: $urn) {
                schemaMetadata {
                    fields {
                        fieldPath
                        upstreamFields {
                            fieldPath
                            dataset {
                                urn
                                name
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            urn = self._to_datahub_urn(dataset_id)
            data = await self._execute_graphql(query, {"urn": urn})

            fields = data.get("dataset", {}).get("schemaMetadata", {}).get("fields", [])

            for field in fields:
                if field.get("fieldPath") == column_name:
                    lineage: list[ColumnLineage] = []
                    for upstream in field.get("upstreamFields", []):
                        source_dataset = upstream.get("dataset", {})
                        if source_dataset:
                            lineage.append(
                                ColumnLineage(
                                    target_dataset=dataset_id,
                                    target_column=column_name,
                                    source_dataset=self._from_datahub_urn(
                                        source_dataset.get("urn", "")
                                    ),
                                    source_column=upstream.get("fieldPath", ""),
                                )
                            )
                    return lineage

            return []
        except httpx.HTTPError:
            return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get job that produces this dataset.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        query = """
        query GetProducingJob($urn: String!) {
            dataset(urn: $urn) {
                upstream: lineage(
                    input: {direction: UPSTREAM, start: 0, count: 10}
                ) {
                    entities {
                        entity {
                            urn
                            ... on DataJob {
                                urn
                                jobId
                                dataFlow { urn }
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            urn = self._to_datahub_urn(dataset_id)
            data = await self._execute_graphql(query, {"urn": urn})

            upstream = data.get("dataset", {}).get("upstream", {}).get("entities", [])

            for entity in upstream:
                e = entity.get("entity", {})
                if e.get("urn", "").startswith("urn:li:dataJob:"):
                    return Job(
                        id=e.get("jobId", e.get("urn", "")),
                        name=e.get("jobId", ""),
                        job_type=JobType.UNKNOWN,
                        outputs=[dataset_id],
                    )

            return None
        except httpx.HTTPError:
            return None

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search DataHub catalog.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Matching datasets.
        """
        search_query = """
        query Search($input: SearchInput!) {
            search(input: $input) {
                searchResults {
                    entity {
                        urn
                        ... on Dataset {
                            name
                            platform { name }
                            properties { description }
                        }
                    }
                }
            }
        }
        """

        try:
            data = await self._execute_graphql(
                search_query,
                {
                    "input": {
                        "type": "DATASET",
                        "query": query,
                        "start": 0,
                        "count": limit,
                    }
                },
            )

            results = data.get("search", {}).get("searchResults", [])
            return [self._api_to_dataset(r.get("entity", {})) for r in results if r.get("entity")]
        except httpx.HTTPError:
            return []

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
            database: Filter by database (not used).
            schema: Filter by schema (not used).
            limit: Maximum results.

        Returns:
            List of datasets.
        """
        query = """
        query ListDatasets($input: SearchInput!) {
            search(input: $input) {
                searchResults {
                    entity {
                        urn
                        ... on Dataset {
                            name
                            platform { name }
                            properties { description }
                        }
                    }
                }
            }
        }
        """

        try:
            search_input: dict[str, Any] = {
                "type": "DATASET",
                "query": "*",
                "start": 0,
                "count": limit,
            }

            if platform:
                search_input["filters"] = [
                    {"field": "platform", "value": f"urn:li:dataPlatform:{platform}"}
                ]

            data = await self._execute_graphql(query, {"input": search_input})

            results = data.get("search", {}).get("searchResults", [])
            return [self._api_to_dataset(r.get("entity", {})) for r in results if r.get("entity")]
        except httpx.HTTPError:
            return []

    # --- Helper methods ---

    def _api_to_dataset(self, data: dict[str, Any]) -> Dataset:
        """Convert DataHub entity to Dataset.

        Args:
            data: DataHub entity response.

        Returns:
            Dataset instance.
        """
        urn = data.get("urn", "")
        name = data.get("name", "")
        platform_data = data.get("platform", {})
        platform = platform_data.get("name", "unknown") if platform_data else "unknown"
        properties = data.get("properties", {}) or {}

        # Parse owners
        owners: list[str] = []
        ownership = data.get("ownership", {})
        if ownership:
            for owner_data in ownership.get("owners", []):
                owner = owner_data.get("owner", {})
                if "username" in owner:
                    owners.append(owner["username"])

        # Parse tags
        tags: list[str] = []
        global_tags = data.get("globalTags", {})
        if global_tags:
            for tag_data in global_tags.get("tags", []):
                tag = tag_data.get("tag", {})
                if "name" in tag:
                    tags.append(tag["name"])

        # Parse name from URN if not provided
        if not name and urn:
            dataset_id = self._from_datahub_urn(urn)
            name = dataset_id.name.split(".")[-1] if "." in dataset_id.name else dataset_id.name

        return Dataset(
            id=self._from_datahub_urn(urn) if urn else DatasetId(platform=platform, name=name),
            name=name.split(".")[-1] if "." in name else name,
            qualified_name=name,
            dataset_type=DatasetType.TABLE,
            platform=platform,
            description=properties.get("description"),
            owners=owners,
            tags=tags,
        )
