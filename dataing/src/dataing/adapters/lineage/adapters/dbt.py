"""dbt lineage adapter.

Supports two modes:
1. Local manifest.json file
2. dbt Cloud API

dbt provides excellent lineage via its manifest.json:
- Model dependencies (ref())
- Source definitions
- Column-level lineage (if docs generated)
- Test associations
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from dataing.adapters.lineage.base import BaseLineageAdapter
from dataing.adapters.lineage.exceptions import LineageParseError
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
    provider_type=LineageProviderType.DBT,
    display_name="dbt",
    description="Lineage from dbt manifest.json or dbt Cloud",
    capabilities=LineageCapabilities(
        supports_column_lineage=True,
        supports_job_runs=True,
        supports_freshness=False,
        supports_search=True,
        supports_owners=True,
        supports_tags=True,
        is_realtime=False,
    ),
    config_schema=LineageConfigSchema(
        fields=[
            LineageConfigField(
                name="manifest_path",
                label="Manifest Path",
                type="string",
                required=False,
                group="local",
                description="Path to local manifest.json file",
            ),
            LineageConfigField(
                name="account_id",
                label="dbt Cloud Account ID",
                type="string",
                required=False,
                group="cloud",
            ),
            LineageConfigField(
                name="project_id",
                label="dbt Cloud Project ID",
                type="string",
                required=False,
                group="cloud",
            ),
            LineageConfigField(
                name="api_key",
                label="dbt Cloud API Key",
                type="secret",
                required=False,
                group="cloud",
            ),
            LineageConfigField(
                name="environment_id",
                label="dbt Cloud Environment ID",
                type="string",
                required=False,
                group="cloud",
            ),
            LineageConfigField(
                name="target_platform",
                label="Target Platform",
                type="string",
                required=True,
                default="snowflake",
                description="Platform where dbt runs (e.g., snowflake, postgres)",
            ),
        ]
    ),
)
class DbtAdapter(BaseLineageAdapter):
    """dbt lineage adapter.

    Config (manifest mode):
        manifest_path: Path to manifest.json

    Config (dbt Cloud mode):
        account_id: dbt Cloud account ID
        project_id: dbt Cloud project ID
        api_key: dbt Cloud API key
        environment_id: Optional environment ID
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the dbt adapter.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self._manifest_path = config.get("manifest_path")
        self._account_id = config.get("account_id")
        self._project_id = config.get("project_id")
        self._api_key = config.get("api_key")
        self._environment_id = config.get("environment_id")
        self._target_platform = config.get("target_platform", "snowflake")

        self._manifest: dict[str, Any] | None = None
        self._client: httpx.AsyncClient | None = None

        if self._api_key:
            self._client = httpx.AsyncClient(
                base_url="https://cloud.getdbt.com/api/v2",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        return LineageCapabilities(
            supports_column_lineage=True,
            supports_job_runs=True,
            supports_freshness=False,
            supports_search=True,
            supports_owners=True,
            supports_tags=True,
            is_realtime=False,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
        return LineageProviderInfo(
            provider=LineageProviderType.DBT,
            display_name="dbt",
            description="Lineage from dbt models and sources",
            capabilities=self.capabilities,
        )

    async def _load_manifest(self) -> dict[str, Any]:
        """Load manifest from file or API.

        Returns:
            The dbt manifest dictionary.

        Raises:
            LineageParseError: If manifest cannot be loaded.
        """
        if self._manifest:
            return self._manifest

        if self._manifest_path:
            try:
                path = Path(self._manifest_path)
                self._manifest = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                raise LineageParseError(self._manifest_path, f"Failed to read manifest: {e}") from e
        elif self._client and self._account_id:
            try:
                # Fetch from dbt Cloud
                response = await self._client.get(
                    f"/accounts/{self._account_id}/runs",
                    params={"project_id": self._project_id, "limit": 1},
                )
                response.raise_for_status()
                runs_data = response.json()
                if not runs_data.get("data"):
                    raise LineageParseError("dbt Cloud", "No runs found")

                latest_run = runs_data["data"][0]

                # Get artifacts from latest run
                artifact_response = await self._client.get(
                    f"/accounts/{self._account_id}/runs/{latest_run['id']}"
                    "/artifacts/manifest.json"
                )
                artifact_response.raise_for_status()
                self._manifest = artifact_response.json()
            except httpx.HTTPError as e:
                raise LineageParseError("dbt Cloud", str(e)) from e
        else:
            raise LineageParseError("dbt", "Either manifest_path or dbt Cloud credentials required")

        return self._manifest

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset from dbt manifest.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Dataset if found, None otherwise.
        """
        manifest = await self._load_manifest()

        # Search in nodes (models, seeds, snapshots)
        for node_id, node in manifest.get("nodes", {}).items():
            if self._matches_dataset(node, dataset_id):
                return self._node_to_dataset(node_id, node)

        # Search in sources
        for source_id, source in manifest.get("sources", {}).items():
            if self._matches_dataset(source, dataset_id):
                return self._source_to_dataset(source_id, source)

        return None

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream datasets using dbt's depends_on.

        Args:
            dataset_id: Dataset to get upstream for.
            depth: How many levels upstream.

        Returns:
            List of upstream datasets.
        """
        manifest = await self._load_manifest()

        # Find the node
        node = self._find_node(manifest, dataset_id)
        if not node:
            return []

        upstream: list[Dataset] = []
        visited: set[str] = set()

        def traverse(n: dict[str, Any], current_depth: int) -> None:
            if current_depth > depth:
                return

            depends_on = n.get("depends_on", {}).get("nodes", [])
            for dep_id in depends_on:
                if dep_id in visited:
                    continue
                visited.add(dep_id)

                if dep_id in manifest.get("nodes", {}):
                    dep_node = manifest["nodes"][dep_id]
                    upstream.append(self._node_to_dataset(dep_id, dep_node))
                    if current_depth < depth:
                        traverse(dep_node, current_depth + 1)
                elif dep_id in manifest.get("sources", {}):
                    dep_source = manifest["sources"][dep_id]
                    upstream.append(self._source_to_dataset(dep_id, dep_source))

        traverse(node, 1)
        return upstream

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream datasets (things that depend on this).

        Args:
            dataset_id: Dataset to get downstream for.
            depth: How many levels downstream.

        Returns:
            List of downstream datasets.
        """
        manifest = await self._load_manifest()

        # Build reverse dependency map
        reverse_deps: dict[str, list[str]] = {}
        for node_id, node in manifest.get("nodes", {}).items():
            for dep_id in node.get("depends_on", {}).get("nodes", []):
                reverse_deps.setdefault(dep_id, []).append(node_id)

        # Find our node's ID
        node_id = self._find_node_id(manifest, dataset_id)
        if not node_id:
            return []

        downstream: list[Dataset] = []
        visited: set[str] = set()

        def traverse(nid: str, current_depth: int) -> None:
            if current_depth > depth:
                return

            for child_id in reverse_deps.get(nid, []):
                if child_id in visited:
                    continue
                visited.add(child_id)

                if child_id in manifest.get("nodes", {}):
                    child_node = manifest["nodes"][child_id]
                    downstream.append(self._node_to_dataset(child_id, child_node))
                    if current_depth < depth:
                        traverse(child_id, current_depth + 1)

        traverse(node_id, 1)
        return downstream

    async def get_column_lineage(
        self,
        dataset_id: DatasetId,
        column_name: str,
    ) -> list[ColumnLineage]:
        """Get column lineage from dbt catalog.

        Args:
            dataset_id: Dataset containing the column.
            column_name: Column to trace.

        Returns:
            List of column lineage mappings.
        """
        # dbt stores column lineage in catalog.json if generated
        # For now, return empty - full implementation would parse SQL
        return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get the dbt model as a job.

        Args:
            dataset_id: Dataset to find producer for.

        Returns:
            Job if found, None otherwise.
        """
        manifest = await self._load_manifest()
        node = self._find_node(manifest, dataset_id)

        if not node:
            return None

        return Job(
            id=node.get("unique_id", ""),
            name=node.get("name", ""),
            job_type=self._get_job_type(node),
            inputs=[
                self._node_id_to_dataset_id(dep_id, manifest)
                for dep_id in node.get("depends_on", {}).get("nodes", [])
            ],
            outputs=[self._node_to_dataset_id(node)],
            source_code_url=self._get_source_url(node),
            source_code_path=node.get("original_file_path"),
            owners=node.get("meta", {}).get("owners", []),
            tags=node.get("tags", []),
        )

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search dbt models by name.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            Matching datasets.
        """
        manifest = await self._load_manifest()
        query_lower = query.lower()
        results: list[Dataset] = []

        for node_id, node in manifest.get("nodes", {}).items():
            if query_lower in node.get("name", "").lower():
                results.append(self._node_to_dataset(node_id, node))
                if len(results) >= limit:
                    break

        return results

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
        manifest = await self._load_manifest()
        results: list[Dataset] = []

        for node_id, node in manifest.get("nodes", {}).items():
            # Apply filters
            if database and node.get("database", "").lower() != database.lower():
                continue
            if schema and node.get("schema", "").lower() != schema.lower():
                continue

            results.append(self._node_to_dataset(node_id, node))
            if len(results) >= limit:
                break

        return results

    # --- Helper methods ---

    def _node_to_dataset(self, node_id: str, node: dict[str, Any]) -> Dataset:
        """Convert dbt node to Dataset.

        Args:
            node_id: Node unique ID.
            node: Node dictionary from manifest.

        Returns:
            Dataset instance.
        """
        return Dataset(
            id=self._node_to_dataset_id(node),
            name=node.get("name", ""),
            qualified_name=(
                f"{node.get('database', '')}.{node.get('schema', '')}."
                f"{node.get('alias', node.get('name', ''))}"
            ),
            dataset_type=self._get_dataset_type(node),
            platform=self._target_platform,
            database=node.get("database"),
            schema=node.get("schema"),
            description=node.get("description"),
            tags=node.get("tags", []),
            owners=node.get("meta", {}).get("owners", []),
            source_code_path=node.get("original_file_path"),
        )

    def _source_to_dataset(self, source_id: str, source: dict[str, Any]) -> Dataset:
        """Convert dbt source to Dataset.

        Args:
            source_id: Source unique ID.
            source: Source dictionary from manifest.

        Returns:
            Dataset instance.
        """
        return Dataset(
            id=DatasetId(
                platform=self._target_platform,
                name=(
                    f"{source.get('database', '')}.{source.get('schema', '')}."
                    f"{source.get('identifier', source.get('name', ''))}"
                ),
            ),
            name=source.get("name", ""),
            qualified_name=(
                f"{source.get('database', '')}.{source.get('schema', '')}."
                f"{source.get('name', '')}"
            ),
            dataset_type=DatasetType.SOURCE,
            platform=self._target_platform,
            database=source.get("database"),
            schema=source.get("schema"),
            description=source.get("description"),
        )

    def _node_to_dataset_id(self, node: dict[str, Any]) -> DatasetId:
        """Convert node to DatasetId.

        Args:
            node: Node dictionary.

        Returns:
            DatasetId instance.
        """
        return DatasetId(
            platform=self._target_platform,
            name=(
                f"{node.get('database', '')}.{node.get('schema', '')}."
                f"{node.get('alias', node.get('name', ''))}"
            ),
        )

    def _node_id_to_dataset_id(self, node_id: str, manifest: dict[str, Any]) -> DatasetId:
        """Convert node ID to DatasetId.

        Args:
            node_id: Node unique ID.
            manifest: Manifest dictionary.

        Returns:
            DatasetId instance.
        """
        if node_id in manifest.get("nodes", {}):
            return self._node_to_dataset_id(manifest["nodes"][node_id])
        elif node_id in manifest.get("sources", {}):
            source = manifest["sources"][node_id]
            return DatasetId(
                platform=self._target_platform,
                name=(
                    f"{source.get('database', '')}.{source.get('schema', '')}."
                    f"{source.get('identifier', source.get('name', ''))}"
                ),
            )
        return DatasetId(platform=self._target_platform, name=node_id)

    def _get_dataset_type(self, node: dict[str, Any]) -> DatasetType:
        """Map dbt resource type to DatasetType.

        Args:
            node: Node dictionary.

        Returns:
            DatasetType enum value.
        """
        resource_type = node.get("resource_type", "")
        mapping: dict[str, DatasetType] = {
            "model": DatasetType.MODEL,
            "seed": DatasetType.SEED,
            "snapshot": DatasetType.SNAPSHOT,
            "source": DatasetType.SOURCE,
        }
        return mapping.get(resource_type, DatasetType.UNKNOWN)

    def _get_job_type(self, node: dict[str, Any]) -> JobType:
        """Map dbt resource type to JobType.

        Args:
            node: Node dictionary.

        Returns:
            JobType enum value.
        """
        resource_type = node.get("resource_type", "")
        mapping: dict[str, JobType] = {
            "model": JobType.DBT_MODEL,
            "test": JobType.DBT_TEST,
            "snapshot": JobType.DBT_SNAPSHOT,
        }
        return mapping.get(resource_type, JobType.UNKNOWN)

    def _matches_dataset(self, node: dict[str, Any], dataset_id: DatasetId) -> bool:
        """Check if dbt node matches dataset ID.

        Args:
            node: Node dictionary.
            dataset_id: Dataset ID to match.

        Returns:
            True if node matches dataset ID.
        """
        node_name = (
            f"{node.get('database', '')}.{node.get('schema', '')}."
            f"{node.get('alias', node.get('name', ''))}"
        )
        result: bool = node_name.lower() == dataset_id.name.lower()
        return result

    def _find_node(self, manifest: dict[str, Any], dataset_id: DatasetId) -> dict[str, Any] | None:
        """Find node in manifest by dataset ID.

        Args:
            manifest: Manifest dictionary.
            dataset_id: Dataset ID to find.

        Returns:
            Node dictionary if found, None otherwise.
        """
        nodes: dict[str, Any] = manifest.get("nodes", {})
        for node in nodes.values():
            if self._matches_dataset(node, dataset_id):
                result: dict[str, Any] = node
                return result
        return None

    def _find_node_id(self, manifest: dict[str, Any], dataset_id: DatasetId) -> str | None:
        """Find node ID in manifest by dataset ID.

        Args:
            manifest: Manifest dictionary.
            dataset_id: Dataset ID to find.

        Returns:
            Node ID if found, None otherwise.
        """
        nodes: dict[str, Any] = manifest.get("nodes", {})
        for node_id, node in nodes.items():
            if self._matches_dataset(node, dataset_id):
                return str(node_id)
        sources: dict[str, Any] = manifest.get("sources", {})
        for source_id, source in sources.items():
            if self._matches_dataset(source, dataset_id):
                return str(source_id)
        return None

    def _get_source_url(self, node: dict[str, Any]) -> str | None:
        """Get source code URL for node.

        Args:
            node: Node dictionary.

        Returns:
            Source code URL if available.
        """
        # Could be populated from meta or external config
        meta: dict[str, Any] = node.get("meta", {})
        url: str | None = meta.get("source_url")
        return url
