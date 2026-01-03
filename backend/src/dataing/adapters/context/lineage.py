"""Lineage client for fetching data lineage information."""

from __future__ import annotations

from typing import Any, TypeAlias

import httpx

from dataing.core.domain_types import LineageContext as CoreLineageContext

# Re-export for convenience - use TypeAlias for proper type checking
LineageContext: TypeAlias = CoreLineageContext


class OpenLineageClient:
    """Fetches lineage from OpenLineage-compatible API.

    This client connects to OpenLineage-compatible endpoints
    to retrieve upstream and downstream dependencies.

    Attributes:
        base_url: Base URL of the OpenLineage API.
    """

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        """Initialize the OpenLineage client.

        Args:
            base_url: Base URL of the OpenLineage API.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_lineage(self, dataset_id: str) -> LineageContext:
        """Get lineage information for a dataset.

        Args:
            dataset_id: Fully qualified table name (namespace.dataset).

        Returns:
            LineageContext with upstream and downstream dependencies.

        Raises:
            httpx.HTTPError: If API call fails.
        """
        # Parse dataset_id into namespace and name
        parts = dataset_id.split(".", 1)
        if len(parts) == 2:
            namespace, name = parts
        else:
            namespace = "default"
            name = dataset_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Fetch upstream lineage
            upstream_response = await client.get(
                f"{self.base_url}/api/v1/lineage/datasets/{namespace}/{name}/upstream"
            )
            upstream_data = upstream_response.json() if upstream_response.is_success else {}

            # Fetch downstream lineage
            downstream_response = await client.get(
                f"{self.base_url}/api/v1/lineage/datasets/{namespace}/{name}/downstream"
            )
            downstream_data = downstream_response.json() if downstream_response.is_success else {}

        return LineageContext(
            target=dataset_id,
            upstream=tuple(self._extract_datasets(upstream_data)),
            downstream=tuple(self._extract_datasets(downstream_data)),
        )

    def _extract_datasets(self, data: dict[str, Any]) -> list[str]:
        """Extract dataset names from OpenLineage response.

        Args:
            data: OpenLineage API response.

        Returns:
            List of dataset identifiers.
        """
        datasets = []
        for item in data.get("datasets", []):
            namespace = item.get("namespace", "")
            name = item.get("name", "")
            if name:
                full_name = f"{namespace}.{name}" if namespace else name
                datasets.append(full_name)
        return datasets


class MockLineageClient:
    """Mock lineage client for testing."""

    def __init__(self, lineage_map: dict[str, LineageContext] | None = None) -> None:
        """Initialize mock client.

        Args:
            lineage_map: Map of dataset IDs to lineage contexts.
        """
        self.lineage_map = lineage_map or {}

    async def get_lineage(self, dataset_id: str) -> LineageContext:
        """Get mock lineage.

        Args:
            dataset_id: Dataset identifier.

        Returns:
            Predefined LineageContext or empty context.
        """
        return self.lineage_map.get(
            dataset_id,
            LineageContext(target=dataset_id, upstream=(), downstream=()),
        )
