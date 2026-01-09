"""Dagster lineage adapter.

Dagster has first-class asset lineage support.
Assets define their dependencies explicitly.
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
    provider_type=LineageProviderType.DAGSTER,
    display_name="Dagster",
    description="Asset lineage from Dagster",
    capabilities=LineageCapabilities(
        supports_column_lineage=False,
        supports_job_runs=True,
        supports_freshness=True,
        supports_search=True,
        supports_owners=True,
        supports_tags=True,
        is_realtime=True,
    ),
    config_schema=LineageConfigSchema(
        fields=[
            LineageConfigField(
                name="base_url",
                label="Dagster WebServer URL",
                type="string",
                required=True,
                placeholder="http://localhost:3000",
            ),
            LineageConfigField(
                name="api_token",
                label="API Token (Dagster Cloud)",
                type="secret",
                required=False,
            ),
        ]
    ),
)
class DagsterAdapter(BaseLineageAdapter):
    """Dagster lineage adapter.

    Config:
        base_url: Dagster webserver/GraphQL URL
        api_token: Optional API token (for Dagster Cloud)

    Uses Dagster's GraphQL API for asset lineage.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the Dagster adapter.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self._base_url = config.get("base_url", "").rstrip("/")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_token = config.get("api_token")
        if api_token:
            headers["Dagster-Cloud-Api-Token"] = api_token

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
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
            is_realtime=True,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
        return LineageProviderInfo(
            provider=LineageProviderType.DAGSTER,
            display_name="Dagster",
            description="Asset lineage from Dagster",
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

        response = await self._client.post("/graphql", json=payload)
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

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get asset metadata from Dagster.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset if found, None otherwise.
        """
        query = """
        query GetAsset($assetKey: AssetKeyInput!) {
            assetOrError(assetKey: $assetKey) {
                ... on Asset {
                    key { path }
                    definition {
                        description
                        owners { ... on TeamAssetOwner { team } }
                        groupName
                        hasMaterializePermission
                    }
                    assetMaterializations(limit: 1) {
                        timestamp
                    }
                }
            }
        }
        """

        try:
            asset_path = dataset_id.name.split(".")
            data = await self._execute_graphql(query, {"assetKey": {"path": asset_path}})

            asset = data.get("assetOrError", {})
            if not asset or "key" not in asset:
                return None

            return self._api_to_dataset(asset)
        except httpx.HTTPError:
            return None

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream assets via GraphQL.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            List of upstream datasets.
        """
        query = """
        query GetAssetLineage($assetKey: AssetKeyInput!) {
            assetOrError(assetKey: $assetKey) {
                ... on Asset {
                    definition {
                        dependencyKeys { path }
                    }
                }
            }
        }
        """

        try:
            asset_path = dataset_id.name.split(".")
            data = await self._execute_graphql(query, {"assetKey": {"path": asset_path}})

            asset = data.get("assetOrError", {})
            definition = asset.get("definition", {})
            dep_keys = definition.get("dependencyKeys", [])

            upstream: list[Dataset] = []
            for dep_key in dep_keys:
                path = dep_key.get("path", [])
                if path:
                    name = ".".join(path)
                    upstream.append(
                        Dataset(
                            id=DatasetId(platform="dagster", name=name),
                            name=path[-1],
                            qualified_name=name,
                            dataset_type=DatasetType.TABLE,
                            platform="dagster",
                        )
                    )

            # Recursively get more levels if needed
            if depth > 1:
                for ds in list(upstream):
                    more_upstream = await self.get_upstream(ds.id, depth=depth - 1)
                    upstream.extend(more_upstream)

            return upstream
        except httpx.HTTPError:
            return []

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream assets via GraphQL.

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            List of downstream datasets.
        """
        query = """
        query GetAssetLineage($assetKey: AssetKeyInput!) {
            assetOrError(assetKey: $assetKey) {
                ... on Asset {
                    definition {
                        dependedByKeys { path }
                    }
                }
            }
        }
        """

        try:
            asset_path = dataset_id.name.split(".")
            data = await self._execute_graphql(query, {"assetKey": {"path": asset_path}})

            asset = data.get("assetOrError", {})
            definition = asset.get("definition", {})
            dep_keys = definition.get("dependedByKeys", [])

            downstream: list[Dataset] = []
            for dep_key in dep_keys:
                path = dep_key.get("path", [])
                if path:
                    name = ".".join(path)
                    downstream.append(
                        Dataset(
                            id=DatasetId(platform="dagster", name=name),
                            name=path[-1],
                            qualified_name=name,
                            dataset_type=DatasetType.TABLE,
                            platform="dagster",
                        )
                    )

            # Recursively get more levels if needed
            if depth > 1:
                for ds in list(downstream):
                    more_downstream = await self.get_downstream(ds.id, depth=depth - 1)
                    downstream.extend(more_downstream)

            return downstream
        except httpx.HTTPError:
            return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get the op that produces this asset.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        query = """
        query GetAssetJob($assetKey: AssetKeyInput!) {
            assetOrError(assetKey: $assetKey) {
                ... on Asset {
                    definition {
                        opNames
                        jobNames
                        dependencyKeys { path }
                    }
                }
            }
        }
        """

        try:
            asset_path = dataset_id.name.split(".")
            data = await self._execute_graphql(query, {"assetKey": {"path": asset_path}})

            asset = data.get("assetOrError", {})
            definition = asset.get("definition", {})

            op_names = definition.get("opNames", [])
            job_names = definition.get("jobNames", [])

            if not op_names and not job_names:
                return None

            return Job(
                id=op_names[0] if op_names else job_names[0],
                name=op_names[0] if op_names else job_names[0],
                job_type=JobType.DAGSTER_OP,
                inputs=[
                    DatasetId(platform="dagster", name=".".join(dep.get("path", [])))
                    for dep in definition.get("dependencyKeys", [])
                ],
                outputs=[dataset_id],
            )
        except httpx.HTTPError:
            return None

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search for assets by name.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Matching datasets.
        """
        graphql_query = """
        query ListAssets {
            assetsOrError {
                ... on AssetConnection {
                    nodes {
                        key { path }
                        definition {
                            description
                            groupName
                        }
                    }
                }
            }
        }
        """

        try:
            data = await self._execute_graphql(graphql_query)
            assets = data.get("assetsOrError", {}).get("nodes", [])

            query_lower = query.lower()
            results: list[Dataset] = []

            for asset in assets:
                path = asset.get("key", {}).get("path", [])
                name = ".".join(path)

                if query_lower in name.lower():
                    results.append(self._api_to_dataset(asset))
                    if len(results) >= limit:
                        break

            return results
        except httpx.HTTPError:
            return []

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """List all assets.

        Args:
            platform: Filter by platform (not used).
            database: Filter by database (not used).
            schema: Filter by schema (not used).
            limit: Maximum results.

        Returns:
            List of datasets.
        """
        query = """
        query ListAssets {
            assetsOrError {
                ... on AssetConnection {
                    nodes {
                        key { path }
                        definition {
                            description
                            groupName
                        }
                    }
                }
            }
        }
        """

        try:
            data = await self._execute_graphql(query)
            assets = data.get("assetsOrError", {}).get("nodes", [])

            return [self._api_to_dataset(a) for a in assets[:limit]]
        except httpx.HTTPError:
            return []

    # --- Helper methods ---

    def _api_to_dataset(self, data: dict[str, Any]) -> Dataset:
        """Convert Dagster asset response to Dataset.

        Args:
            data: Dagster asset response.

        Returns:
            Dataset instance.
        """
        key = data.get("key", {})
        path = key.get("path", [])
        name = ".".join(path) if path else ""

        definition = data.get("definition", {})

        owners: list[str] = []
        for owner in definition.get("owners", []):
            if "team" in owner:
                owners.append(owner["team"])

        return Dataset(
            id=DatasetId(platform="dagster", name=name),
            name=path[-1] if path else "",
            qualified_name=name,
            dataset_type=DatasetType.TABLE,
            platform="dagster",
            description=definition.get("description"),
            owners=owners,
            tags=[definition.get("groupName")] if definition.get("groupName") else [],
        )
