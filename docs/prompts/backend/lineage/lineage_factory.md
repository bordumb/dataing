# DataDr Lineage Provider Adapter Layer: Technical Specification

## Executive Summary

This specification defines a pluggable lineage adapter architecture that normalizes different lineage sources (dbt, OpenLineage, Airflow, Dagster, DataHub, etc.) into a unified interface. The investigation engine can answer "where did this data come from?" and "what depends on this?" regardless of which orchestration/catalog tools the customer uses.

**Core Principle:** Unified lineage graph from heterogeneous sources.

---

## 1. Why This Matters

| Customer Type | Tools | Lineage Source |
|---------------|-------|----------------|
| Modern Data Stack | dbt + Airflow | dbt manifest + Airflow metadata |
| Enterprise (Legacy) | Informatica + custom ETL | OpenLineage events |
| Data Platform Team | Dagster | Dagster asset lineage |
| Spark-heavy | Spark + Airflow | OpenLineage (Spark integration) |
| Catalog-first | DataHub or Atlan | Catalog's lineage API |
| Simple | Just SQL scripts | Static analysis (parse SQL) |

**The Problem:** Customer has data quality issue in `analytics.orders`. They need to know:
1. What upstream tables feed into it?
2. What jobs/models produce it?
3. What downstream dashboards/tables break if it's wrong?
4. When did it last run successfully?

Without lineage integration, DataDr can only guess via SQL parsing.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INVESTIGATION ENGINE                               │
│                                                                              │
│   "Table analytics.orders has NULL spike. What's the root cause?"           │
│                                                                              │
│   lineage = await self.lineage.get_upstream("analytics.orders")             │
│   # Returns: [raw.events, raw.users] regardless of source                   │
│                                                                              │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LINEAGE ADAPTER LAYER                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      LineageAdapter (Protocol)                           ││
│  │                                                                          ││
│  │  get_upstream(dataset) -> list[Dataset]                                 ││
│  │  get_downstream(dataset) -> list[Dataset]                               ││
│  │  get_lineage_graph(dataset, depth) -> LineageGraph                      ││
│  │  get_producing_job(dataset) -> Job | None                               ││
│  │  get_consuming_jobs(dataset) -> list[Job]                               ││
│  │  get_column_lineage(dataset, column) -> list[ColumnLineage]             ││
│  │  search_datasets(query) -> list[Dataset]                                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│      ┌───────────┬────────────┬────┴─────┬────────────┬───────────┐        │
│      ▼           ▼            ▼          ▼            ▼           ▼        │
│  ┌───────┐  ┌────────┐  ┌─────────┐  ┌───────┐  ┌─────────┐  ┌────────┐  │
│  │  dbt  │  │OpenLine│  │ Airflow │  │Dagster│  │ DataHub │  │ Static │  │
│  │Adapter│  │  age   │  │ Adapter │  │Adapter│  │ Adapter │  │Analysis│  │
│  └───┬───┘  └────┬───┘  └────┬────┘  └───┬───┘  └────┬────┘  └────┬───┘  │
│      │           │           │           │           │            │        │
└──────┼───────────┼───────────┼───────────┼───────────┼────────────┼────────┘
       │           │           │           │           │            │
       ▼           ▼           ▼           ▼           ▼            ▼
  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
  │  dbt    │ │ Marquez │ │ Airflow │ │ Dagster │ │ DataHub │ │   SQL   │
  │manifest │ │   API   │ │   API   │ │   API   │ │ GraphQL │ │ Parser  │
  │  .json  │ │         │ │         │ │         │ │         │ │         │
  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
```

---

## 3. Directory Structure

```
backend/src/datadr/lineage/
├── __init__.py
├── types.py                    # Unified types (Dataset, Job, LineageGraph, etc.)
├── protocols.py                # LineageAdapter protocol definition
├── registry.py                 # Lineage adapter registry
├── exceptions.py               # Lineage-specific exceptions
├── graph.py                    # Graph utilities (traversal, merging)
│
├── adapters/
│   ├── __init__.py
│   ├── base.py                 # Base class with shared logic
│   ├── dbt.py                  # dbt manifest.json / dbt Cloud API
│   ├── openlineage.py          # OpenLineage / Marquez API
│   ├── airflow.py              # Airflow REST API
│   ├── dagster.py              # Dagster GraphQL API
│   ├── datahub.py              # DataHub GraphQL API
│   ├── openmetadata.py         # OpenMetadata REST API
│   ├── atlan.py                # Atlan REST API
│   ├── static_sql.py           # SQL parsing fallback
│   └── composite.py            # Merges multiple sources
│
├── parsers/
│   ├── __init__.py
│   ├── sql_parser.py           # Extract lineage from SQL (sqlglot)
│   └── dbt_manifest.py         # Parse dbt manifest.json
│
└── config/
    ├── __init__.py
    └── schemas.py              # Config schemas for each provider
```

---

## 4. Unified Types

### 4.1 Core Types

```python
# backend/src/datadr/lineage/types.py

"""Unified types for lineage information.

These types normalize the differences between lineage providers.
All adapters convert to/from these types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DatasetType(str, Enum):
    """Type of dataset."""
    TABLE = "table"
    VIEW = "view"
    EXTERNAL = "external"
    SEED = "seed"              # dbt seed
    SOURCE = "source"          # External source
    MODEL = "model"            # dbt model / transformed
    SNAPSHOT = "snapshot"      # dbt snapshot
    FILE = "file"              # S3/GCS file
    STREAM = "stream"          # Kafka topic, etc.
    UNKNOWN = "unknown"


class JobType(str, Enum):
    """Type of job/process."""
    DBT_MODEL = "dbt_model"
    DBT_TEST = "dbt_test"
    DBT_SNAPSHOT = "dbt_snapshot"
    AIRFLOW_TASK = "airflow_task"
    DAGSTER_OP = "dagster_op"
    SPARK_JOB = "spark_job"
    SQL_QUERY = "sql_query"
    PYTHON_SCRIPT = "python_script"
    FIVETRAN_SYNC = "fivetran_sync"
    AIRBYTE_SYNC = "airbyte_sync"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    """Status of a job run."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class DatasetId:
    """Unique identifier for a dataset.

    Uses a URN-like format for consistency across providers.
    """
    platform: str          # "snowflake", "postgres", "s3", etc.
    name: str              # Fully qualified: "database.schema.table"

    def __str__(self) -> str:
        return f"{self.platform}://{self.name}"

    @classmethod
    def from_urn(cls, urn: str) -> "DatasetId":
        """Parse from URN string."""
        # Handle formats:
        # - "snowflake://db.schema.table"
        # - "urn:li:dataset:(urn:li:dataPlatform:snowflake,db.schema.table,PROD)"
        if urn.startswith("urn:li:dataset:"):
            # DataHub format
            parts = urn.split(",")
            platform = parts[0].split(":")[-1]
            name = parts[1]
            return cls(platform=platform, name=name)
        elif "://" in urn:
            # Simple format
            platform, name = urn.split("://", 1)
            return cls(platform=platform, name=name)
        else:
            return cls(platform="unknown", name=urn)


@dataclass
class Dataset:
    """A dataset (table, view, file, etc.) in the lineage graph."""
    id: DatasetId
    name: str                           # Short name: "orders"
    qualified_name: str                 # Full name: "analytics.public.orders"
    dataset_type: DatasetType

    # Location info
    platform: str                       # "snowflake", "postgres", "dbt"
    database: str | None = None
    schema: str | None = None

    # Metadata
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)

    # Code linkage (if known)
    source_code_url: str | None = None  # GitHub link to producing code
    source_code_path: str | None = None # Relative path in repo

    # Freshness
    last_modified: datetime | None = None
    row_count: int | None = None

    # Provider-specific metadata
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Column:
    """A column within a dataset."""
    name: str
    data_type: str
    description: str | None = None
    is_primary_key: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class ColumnLineage:
    """Lineage for a specific column."""
    target_dataset: DatasetId
    target_column: str
    source_dataset: DatasetId
    source_column: str
    transformation: str | None = None   # SQL expression if known
    confidence: float = 1.0             # 1.0 = certain, <1.0 = inferred


@dataclass
class Job:
    """A job/process that produces or consumes datasets."""
    id: str
    name: str
    job_type: JobType

    # What it reads/writes
    inputs: list[DatasetId] = field(default_factory=list)
    outputs: list[DatasetId] = field(default_factory=list)

    # Code linkage
    source_code_url: str | None = None
    source_code_path: str | None = None

    # Scheduling
    schedule: str | None = None         # Cron expression

    # Ownership
    owners: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # Provider-specific
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobRun:
    """A single execution of a job."""
    id: str
    job_id: str
    status: RunStatus
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = None

    # What was actually read/written
    inputs: list[DatasetId] = field(default_factory=list)
    outputs: list[DatasetId] = field(default_factory=list)

    # Error info (if failed)
    error_message: str | None = None

    # Links
    logs_url: str | None = None

    # Provider-specific
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageEdge:
    """An edge in the lineage graph."""
    source: DatasetId
    target: DatasetId
    job: Job | None = None              # Job that creates this edge
    edge_type: str = "transforms"       # "transforms", "copies", "derives"

    # Column-level lineage (if available)
    column_lineage: list[ColumnLineage] = field(default_factory=list)


@dataclass
class LineageGraph:
    """A lineage graph centered on a dataset."""
    root: DatasetId
    datasets: dict[str, Dataset]        # id string -> Dataset
    edges: list[LineageEdge]
    jobs: dict[str, Job]                # job_id -> Job

    # Traversal helpers
    def get_upstream(self, dataset_id: DatasetId, depth: int = 1) -> list[Dataset]:
        """Get datasets upstream of the given dataset."""
        ...

    def get_downstream(self, dataset_id: DatasetId, depth: int = 1) -> list[Dataset]:
        """Get datasets downstream of the given dataset."""
        ...

    def get_path(self, source: DatasetId, target: DatasetId) -> list[LineageEdge] | None:
        """Find path between two datasets."""
        ...

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for API responses."""
        ...
```

### 4.2 Capability Types

```python
# Continuation of types.py

@dataclass(frozen=True)
class LineageCapabilities:
    """What this lineage provider can do."""
    supports_column_lineage: bool = False
    supports_job_runs: bool = False
    supports_freshness: bool = False
    supports_search: bool = False
    supports_owners: bool = False
    supports_tags: bool = False

    # Depth limits
    max_upstream_depth: int | None = None
    max_downstream_depth: int | None = None

    # Update frequency
    is_realtime: bool = False           # True for OpenLineage, False for dbt manifest


@dataclass(frozen=True)
class LineageProviderInfo:
    """Information about a lineage provider."""
    provider: str
    display_name: str
    description: str
    capabilities: LineageCapabilities
```

---

## 5. Protocol Definition

```python
# backend/src/datadr/lineage/protocols.py

"""Lineage Adapter Protocol.

All lineage adapters implement this protocol, providing a unified
interface regardless of the underlying provider.
"""

from typing import Protocol, runtime_checkable

from datadr.lineage.types import (
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
    """Protocol for lineage adapters."""

    @property
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        ...

    @property
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
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
            ColumnLineageNotSupportedError: If provider doesn't support column lineage.
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
```

---

## 6. Exceptions

```python
# backend/src/datadr/lineage/exceptions.py

"""Lineage-specific exceptions."""


class LineageError(Exception):
    """Base exception for lineage errors."""
    pass


class DatasetNotFoundError(LineageError):
    """Dataset not found in lineage provider."""
    def __init__(self, dataset_id: str):
        super().__init__(f"Dataset not found: {dataset_id}")
        self.dataset_id = dataset_id


class ColumnLineageNotSupportedError(LineageError):
    """Provider doesn't support column-level lineage."""
    pass


class LineageProviderConnectionError(LineageError):
    """Failed to connect to lineage provider."""
    pass


class LineageProviderAuthError(LineageError):
    """Authentication failed for lineage provider."""
    pass


class LineageDepthExceededError(LineageError):
    """Requested lineage depth exceeds provider limits."""
    def __init__(self, requested: int, maximum: int):
        super().__init__(f"Requested depth {requested} exceeds maximum {maximum}")
        self.requested = requested
        self.maximum = maximum
```

---

## 7. Base Adapter

```python
# backend/src/datadr/lineage/adapters/base.py

"""Base lineage adapter with shared logic."""

from abc import ABC, abstractmethod

from datadr.lineage.types import (
    ColumnLineage,
    Dataset,
    DatasetId,
    Job,
    JobRun,
    LineageCapabilities,
    LineageGraph,
    LineageProviderInfo,
)
from datadr.lineage.exceptions import ColumnLineageNotSupportedError


class BaseLineageAdapter(ABC):
    """Base class for lineage adapters.

    Provides:
    - Default implementations for optional methods
    - Capability checking
    - Common utilities
    """

    @property
    @abstractmethod
    def capabilities(self) -> LineageCapabilities:
        """Get provider capabilities."""
        ...

    @property
    @abstractmethod
    def provider_info(self) -> LineageProviderInfo:
        """Get provider information."""
        ...

    @abstractmethod
    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream datasets. Must be implemented."""
        ...

    @abstractmethod
    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream datasets. Must be implemented."""
        ...

    # --- Default implementations ---

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Default: Return None (not found)."""
        return None

    async def get_lineage_graph(
        self,
        dataset_id: DatasetId,
        upstream_depth: int = 3,
        downstream_depth: int = 3,
    ) -> LineageGraph:
        """Default: Build graph by traversing upstream/downstream."""
        from datadr.lineage.graph import build_graph_from_traversal

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
        """Default: Raise not supported."""
        if not self.capabilities.supports_column_lineage:
            raise ColumnLineageNotSupportedError(
                f"Provider {self.provider_info.provider} does not support column lineage"
            )
        return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Default: Return None."""
        return None

    async def get_consuming_jobs(self, dataset_id: DatasetId) -> list[Job]:
        """Default: Return empty list."""
        return []

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Default: Return empty list."""
        return []

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Default: Return empty list."""
        return []

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """Default: Return empty list."""
        return []
```

---

## 8. dbt Adapter

```python
# backend/src/datadr/lineage/adapters/dbt.py

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

import json
from pathlib import Path
from typing import Any

import httpx

from datadr.lineage.adapters.base import BaseLineageAdapter
from datadr.lineage.types import (
    ColumnLineage,
    Dataset,
    DatasetId,
    DatasetType,
    Job,
    JobType,
    LineageCapabilities,
    LineageProviderInfo,
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

    def __init__(
        self,
        # Manifest mode
        manifest_path: str | None = None,
        # dbt Cloud mode
        account_id: str | None = None,
        project_id: str | None = None,
        api_key: str | None = None,
        environment_id: str | None = None,
        # Common
        target_platform: str = "snowflake",  # Platform where dbt runs
        **kwargs,
    ):
        self._manifest_path = manifest_path
        self._account_id = account_id
        self._project_id = project_id
        self._api_key = api_key
        self._environment_id = environment_id
        self._target_platform = target_platform

        self._manifest: dict[str, Any] | None = None
        self._client: httpx.AsyncClient | None = None

        if api_key:
            self._client = httpx.AsyncClient(
                base_url="https://cloud.getdbt.com/api/v2",
                headers={"Authorization": f"Bearer {api_key}"},
            )

    @property
    def capabilities(self) -> LineageCapabilities:
        return LineageCapabilities(
            supports_column_lineage=True,   # If catalog.json available
            supports_job_runs=True,         # dbt Cloud only
            supports_freshness=False,
            supports_search=True,
            supports_owners=True,           # From meta config
            supports_tags=True,             # From tags config
            is_realtime=False,              # Static manifest
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        return LineageProviderInfo(
            provider="dbt",
            display_name="dbt",
            description="Lineage from dbt models and sources",
            capabilities=self.capabilities,
        )

    async def _load_manifest(self) -> dict[str, Any]:
        """Load manifest from file or API."""
        if self._manifest:
            return self._manifest

        if self._manifest_path:
            path = Path(self._manifest_path)
            self._manifest = json.loads(path.read_text())
        elif self._client:
            # Fetch from dbt Cloud
            response = await self._client.get(
                f"/accounts/{self._account_id}/runs",
                params={"project_id": self._project_id, "limit": 1},
            )
            response.raise_for_status()
            latest_run = response.json()["data"][0]

            # Get artifacts from latest run
            artifact_response = await self._client.get(
                f"/accounts/{self._account_id}/runs/{latest_run['id']}/artifacts/manifest.json"
            )
            self._manifest = artifact_response.json()
        else:
            raise ValueError("Either manifest_path or dbt Cloud credentials required")

        return self._manifest

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset from dbt manifest."""
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
        """Get upstream datasets using dbt's depends_on."""
        manifest = await self._load_manifest()

        # Find the node
        node = self._find_node(manifest, dataset_id)
        if not node:
            return []

        upstream = []
        visited = set()

        def traverse(n: dict, current_depth: int):
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
        """Get downstream datasets (things that depend on this)."""
        manifest = await self._load_manifest()

        # Build reverse dependency map
        # This is O(n) but manifests are typically small enough
        reverse_deps: dict[str, list[str]] = {}
        for node_id, node in manifest.get("nodes", {}).items():
            for dep_id in node.get("depends_on", {}).get("nodes", []):
                reverse_deps.setdefault(dep_id, []).append(node_id)

        # Find our node's ID
        node_id = self._find_node_id(manifest, dataset_id)
        if not node_id:
            return []

        downstream = []
        visited = set()

        def traverse(nid: str, current_depth: int):
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
        """Get column lineage from dbt catalog."""
        # dbt stores column lineage in catalog.json if generated
        # This requires parsing the compiled SQL or using dbt's column-level lineage
        # For now, return empty - full implementation would parse SQL
        return []

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get the dbt model as a job."""
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
        """Search dbt models by name."""
        manifest = await self._load_manifest()
        query_lower = query.lower()
        results = []

        for node_id, node in manifest.get("nodes", {}).items():
            if query_lower in node.get("name", "").lower():
                results.append(self._node_to_dataset(node_id, node))
                if len(results) >= limit:
                    break

        return results

    # --- Helper methods ---

    def _node_to_dataset(self, node_id: str, node: dict) -> Dataset:
        """Convert dbt node to Dataset."""
        return Dataset(
            id=self._node_to_dataset_id(node),
            name=node.get("name", ""),
            qualified_name=f"{node.get('database', '')}.{node.get('schema', '')}.{node.get('alias', node.get('name', ''))}",
            dataset_type=self._get_dataset_type(node),
            platform=self._target_platform,
            database=node.get("database"),
            schema=node.get("schema"),
            description=node.get("description"),
            tags=node.get("tags", []),
            owners=node.get("meta", {}).get("owners", []),
            source_code_path=node.get("original_file_path"),
        )

    def _source_to_dataset(self, source_id: str, source: dict) -> Dataset:
        """Convert dbt source to Dataset."""
        return Dataset(
            id=DatasetId(
                platform=self._target_platform,
                name=f"{source.get('database', '')}.{source.get('schema', '')}.{source.get('identifier', source.get('name', ''))}",
            ),
            name=source.get("name", ""),
            qualified_name=f"{source.get('database', '')}.{source.get('schema', '')}.{source.get('name', '')}",
            dataset_type=DatasetType.SOURCE,
            platform=self._target_platform,
            database=source.get("database"),
            schema=source.get("schema"),
            description=source.get("description"),
        )

    def _node_to_dataset_id(self, node: dict) -> DatasetId:
        """Convert node to DatasetId."""
        return DatasetId(
            platform=self._target_platform,
            name=f"{node.get('database', '')}.{node.get('schema', '')}.{node.get('alias', node.get('name', ''))}",
        )

    def _get_dataset_type(self, node: dict) -> DatasetType:
        """Map dbt resource type to DatasetType."""
        resource_type = node.get("resource_type", "")
        mapping = {
            "model": DatasetType.MODEL,
            "seed": DatasetType.SEED,
            "snapshot": DatasetType.SNAPSHOT,
            "source": DatasetType.SOURCE,
        }
        return mapping.get(resource_type, DatasetType.UNKNOWN)

    def _get_job_type(self, node: dict) -> JobType:
        """Map dbt resource type to JobType."""
        resource_type = node.get("resource_type", "")
        mapping = {
            "model": JobType.DBT_MODEL,
            "test": JobType.DBT_TEST,
            "snapshot": JobType.DBT_SNAPSHOT,
        }
        return mapping.get(resource_type, JobType.UNKNOWN)

    def _matches_dataset(self, node: dict, dataset_id: DatasetId) -> bool:
        """Check if dbt node matches dataset ID."""
        node_name = f"{node.get('database', '')}.{node.get('schema', '')}.{node.get('alias', node.get('name', ''))}"
        return node_name.lower() == dataset_id.name.lower()

    def _find_node(self, manifest: dict, dataset_id: DatasetId) -> dict | None:
        """Find node in manifest by dataset ID."""
        for node in manifest.get("nodes", {}).values():
            if self._matches_dataset(node, dataset_id):
                return node
        return None

    def _find_node_id(self, manifest: dict, dataset_id: DatasetId) -> str | None:
        """Find node ID in manifest by dataset ID."""
        for node_id, node in manifest.get("nodes", {}).items():
            if self._matches_dataset(node, dataset_id):
                return node_id
        return None
```

---

## 9. OpenLineage / Marquez Adapter

```python
# backend/src/datadr/lineage/adapters/openlineage.py

"""OpenLineage / Marquez adapter.

OpenLineage is an open standard for lineage metadata.
Marquez is the reference implementation backend.

OpenLineage captures runtime lineage from:
- Spark jobs
- Airflow tasks
- dbt runs
- Custom integrations
"""

import httpx

from datadr.lineage.adapters.base import BaseLineageAdapter
from datadr.lineage.types import (
    Dataset,
    DatasetId,
    DatasetType,
    Job,
    JobRun,
    JobType,
    LineageCapabilities,
    LineageProviderInfo,
    RunStatus,
)


class OpenLineageAdapter(BaseLineageAdapter):
    """OpenLineage / Marquez adapter.

    Config:
        base_url: Marquez API URL (e.g., http://localhost:5000)
        namespace: Default namespace for queries
        api_key: Optional API key for authentication
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        namespace: str = "default",
        api_key: str | None = None,
        **kwargs,
    ):
        self._base_url = base_url.rstrip("/")
        self._namespace = namespace

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v1",
            headers=headers,
        )

    @property
    def capabilities(self) -> LineageCapabilities:
        return LineageCapabilities(
            supports_column_lineage=True,   # OpenLineage supports column lineage
            supports_job_runs=True,         # Full run history
            supports_freshness=True,        # Via run timestamps
            supports_search=True,
            supports_owners=False,          # Not in OpenLineage spec
            supports_tags=True,             # Via facets
            is_realtime=True,               # Events in real-time
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        return LineageProviderInfo(
            provider="openlineage",
            display_name="OpenLineage (Marquez)",
            description="Runtime lineage from Spark, Airflow, dbt, and more",
            capabilities=self.capabilities,
        )

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset from Marquez."""
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
        """Get upstream datasets from Marquez lineage API."""
        response = await self._client.get(
            f"/lineage",
            params={
                "nodeId": f"dataset:{self._namespace}:{dataset_id.name}",
                "depth": depth,
            },
        )
        response.raise_for_status()

        lineage = response.json()
        return self._extract_upstream(lineage, dataset_id)

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream datasets from Marquez lineage API."""
        response = await self._client.get(
            f"/lineage",
            params={
                "nodeId": f"dataset:{self._namespace}:{dataset_id.name}",
                "depth": depth,
            },
        )
        response.raise_for_status()

        lineage = response.json()
        return self._extract_downstream(lineage, dataset_id)

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get job that produces this dataset."""
        dataset = await self.get_dataset(dataset_id)
        if not dataset or not dataset.extra.get("produced_by"):
            return None

        job_name = dataset.extra["produced_by"]
        response = await self._client.get(
            f"/namespaces/{self._namespace}/jobs/{job_name}"
        )
        response.raise_for_status()

        return self._api_to_job(response.json())

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Get recent runs of a job."""
        response = await self._client.get(
            f"/namespaces/{self._namespace}/jobs/{job_id}/runs",
            params={"limit": limit},
        )
        response.raise_for_status()

        runs = response.json().get("runs", [])
        return [self._api_to_run(r) for r in runs]

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search datasets in Marquez."""
        response = await self._client.get(
            "/search",
            params={"q": query, "filter": "dataset", "limit": limit},
        )
        response.raise_for_status()

        results = response.json().get("results", [])
        return [self._api_to_dataset(r) for r in results]

    async def list_datasets(
        self,
        platform: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[Dataset]:
        """List datasets in namespace."""
        response = await self._client.get(
            f"/namespaces/{self._namespace}/datasets",
            params={"limit": limit},
        )
        response.raise_for_status()

        datasets = response.json().get("datasets", [])
        return [self._api_to_dataset(d) for d in datasets]

    # --- Helper methods ---

    def _api_to_dataset(self, data: dict) -> Dataset:
        """Convert Marquez API response to Dataset."""
        name = data.get("name", "")
        parts = name.split(".")

        return Dataset(
            id=DatasetId(
                platform=data.get("sourceName", "unknown"),
                name=name,
            ),
            name=parts[-1] if parts else name,
            qualified_name=name,
            dataset_type=DatasetType.TABLE,  # Marquez doesn't distinguish
            platform=data.get("sourceName", "unknown"),
            database=parts[0] if len(parts) > 2 else None,
            schema=parts[1] if len(parts) > 2 else (parts[0] if len(parts) > 1 else None),
            description=data.get("description"),
            tags=[t.get("name", "") for t in data.get("tags", [])],
            last_modified=data.get("updatedAt"),
            extra={
                "produced_by": data.get("currentVersion", {}).get("run", {}).get("jobName"),
            },
        )

    def _api_to_job(self, data: dict) -> Job:
        """Convert Marquez job response to Job."""
        return Job(
            id=data.get("name", ""),
            name=data.get("name", ""),
            job_type=JobType.UNKNOWN,  # Would need to infer from facets
            inputs=[
                DatasetId(platform="unknown", name=i.get("name", ""))
                for i in data.get("inputs", [])
            ],
            outputs=[
                DatasetId(platform="unknown", name=o.get("name", ""))
                for o in data.get("outputs", [])
            ],
            source_code_url=data.get("facets", {}).get("sourceCodeLocation", {}).get("url"),
        )

    def _api_to_run(self, data: dict) -> JobRun:
        """Convert Marquez run response to JobRun."""
        state = data.get("state", "").upper()
        status_map = {
            "RUNNING": RunStatus.RUNNING,
            "COMPLETED": RunStatus.SUCCESS,
            "FAILED": RunStatus.FAILED,
            "ABORTED": RunStatus.CANCELLED,
        }

        return JobRun(
            id=data.get("id", ""),
            job_id=data.get("jobName", ""),
            status=status_map.get(state, RunStatus.FAILED),
            started_at=data.get("startedAt"),
            ended_at=data.get("endedAt"),
            duration_seconds=data.get("durationMs", 0) / 1000 if data.get("durationMs") else None,
        )

    def _extract_upstream(self, lineage: dict, dataset_id: DatasetId) -> list[Dataset]:
        """Extract upstream datasets from lineage graph."""
        # Marquez returns a graph structure
        # Need to traverse edges to find upstream
        ...

    def _extract_downstream(self, lineage: dict, dataset_id: DatasetId) -> list[Dataset]:
        """Extract downstream datasets from lineage graph."""
        ...
```

---

## 10. Airflow Adapter (Skeleton)

```python
# backend/src/datadr/lineage/adapters/airflow.py

"""Airflow lineage adapter.

Gets lineage from Airflow's metadata database or REST API.
Airflow 2.x has lineage support via inlets/outlets on operators.
"""

import httpx

from datadr.lineage.adapters.base import BaseLineageAdapter
from datadr.lineage.types import (
    Dataset,
    DatasetId,
    Job,
    JobRun,
    LineageCapabilities,
    LineageProviderInfo,
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

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        **kwargs,
    ):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/v1",
            auth=(username, password),
        )

    @property
    def capabilities(self) -> LineageCapabilities:
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
        return LineageProviderInfo(
            provider="airflow",
            display_name="Apache Airflow",
            description="Lineage from Airflow DAGs (inlets/outlets)",
            capabilities=self.capabilities,
        )

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream from Airflow's dataset dependencies."""
        # Airflow 2.4+ has Datasets feature
        # Query /datasets/{uri}/events to find producing tasks
        ...

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream from Airflow's dataset dependencies."""
        ...

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Find task that produces this dataset."""
        # Query datasets API to find producing DAG/task
        ...

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Get recent DAG runs."""
        # job_id format: "dag_id/task_id" or just "dag_id"
        dag_id = job_id.split("/")[0]

        response = await self._client.get(
            f"/dags/{dag_id}/dagRuns",
            params={"limit": limit, "order_by": "-execution_date"},
        )
        response.raise_for_status()

        runs = response.json().get("dag_runs", [])
        return [self._api_to_run(r, dag_id) for r in runs]
```

---

## 11. Dagster Adapter (Skeleton)

```python
# backend/src/datadr/lineage/adapters/dagster.py

"""Dagster lineage adapter.

Dagster has first-class asset lineage support.
Assets define their dependencies explicitly.
"""

import httpx

from datadr.lineage.adapters.base import BaseLineageAdapter
from datadr.lineage.types import (
    Dataset,
    DatasetId,
    Job,
    LineageCapabilities,
    LineageProviderInfo,
)


class DagsterAdapter(BaseLineageAdapter):
    """Dagster lineage adapter.

    Config:
        base_url: Dagster webserver/GraphQL URL
        api_token: Optional API token

    Uses Dagster's GraphQL API for asset lineage.
    """

    def __init__(
        self,
        base_url: str,
        api_token: str | None = None,
        **kwargs,
    ):
        self._base_url = base_url.rstrip("/")
        headers = {}
        if api_token:
            headers["Dagster-Cloud-Api-Token"] = api_token

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
        )

    @property
    def capabilities(self) -> LineageCapabilities:
        return LineageCapabilities(
            supports_column_lineage=False,  # Dagster doesn't track column lineage
            supports_job_runs=True,
            supports_freshness=True,        # Via asset observations
            supports_search=True,
            supports_owners=True,
            supports_tags=True,
            is_realtime=True,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        return LineageProviderInfo(
            provider="dagster",
            display_name="Dagster",
            description="Asset lineage from Dagster",
            capabilities=self.capabilities,
        )

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream assets via GraphQL."""
        query = """
        query AssetLineage($assetKey: AssetKeyInput!) {
            assetOrError(assetKey: $assetKey) {
                ... on Asset {
                    definition {
                        dependencyKeys {
                            path
                        }
                    }
                }
            }
        }
        """

        response = await self._client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {"assetKey": {"path": dataset_id.name.split(".")}},
            },
        )
        response.raise_for_status()

        # Parse and convert to Dataset list
        ...

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream assets via GraphQL."""
        query = """
        query AssetLineage($assetKey: AssetKeyInput!) {
            assetOrError(assetKey: $assetKey) {
                ... on Asset {
                    definition {
                        dependedByKeys {
                            path
                        }
                    }
                }
            }
        }
        """
        ...
```

---

## 12. DataHub Adapter (Skeleton)

```python
# backend/src/datadr/lineage/adapters/datahub.py

"""DataHub lineage adapter.

DataHub is a metadata platform with rich lineage support.
Uses GraphQL API for queries.
"""

import httpx

from datadr.lineage.adapters.base import BaseLineageAdapter
from datadr.lineage.types import (
    ColumnLineage,
    Dataset,
    DatasetId,
    Job,
    LineageCapabilities,
    LineageProviderInfo,
)


class DataHubAdapter(BaseLineageAdapter):
    """DataHub lineage adapter.

    Config:
        base_url: DataHub GMS URL
        token: DataHub access token
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        **kwargs,
    ):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/api/graphql",
            headers={"Authorization": f"Bearer {token}"},
        )

    @property
    def capabilities(self) -> LineageCapabilities:
        return LineageCapabilities(
            supports_column_lineage=True,   # DataHub has fine-grained lineage
            supports_job_runs=True,
            supports_freshness=True,
            supports_search=True,           # Excellent search
            supports_owners=True,
            supports_tags=True,
            is_realtime=False,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        return LineageProviderInfo(
            provider="datahub",
            display_name="DataHub",
            description="Lineage from DataHub metadata platform",
            capabilities=self.capabilities,
        )

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream via DataHub GraphQL."""
        query = """
        query GetUpstream($urn: String!, $depth: Int!) {
            dataset(urn: $urn) {
                upstream: lineage(input: {direction: UPSTREAM, depth: $depth}) {
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

        urn = self._to_datahub_urn(dataset_id)
        response = await self._client.post(
            "",
            json={"query": query, "variables": {"urn": urn, "depth": depth}},
        )
        response.raise_for_status()

        # Parse GraphQL response
        ...

    async def get_column_lineage(
        self,
        dataset_id: DatasetId,
        column_name: str,
    ) -> list[ColumnLineage]:
        """Get column-level lineage from DataHub."""
        query = """
        query GetColumnLineage($urn: String!) {
            dataset(urn: $urn) {
                schemaMetadata {
                    fields {
                        fieldPath
                        upstreams {
                            sourceField {
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
        }
        """
        ...

    async def search_datasets(self, query: str, limit: int = 20) -> list[Dataset]:
        """Search DataHub catalog."""
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
        ...

    def _to_datahub_urn(self, dataset_id: DatasetId) -> str:
        """Convert DatasetId to DataHub URN format."""
        return f"urn:li:dataset:(urn:li:dataPlatform:{dataset_id.platform},{dataset_id.name},PROD)"
```

---

## 13. Static SQL Analysis Adapter

```python
# backend/src/datadr/lineage/adapters/static_sql.py

"""Static SQL analysis adapter.

Fallback when no lineage provider is configured.
Parses SQL to extract table references.

Uses sqlglot for SQL parsing.
"""

from datadr.lineage.adapters.base import BaseLineageAdapter
from datadr.lineage.parsers.sql_parser import SQLLineageParser
from datadr.lineage.types import (
    Dataset,
    DatasetId,
    DatasetType,
    Job,
    JobType,
    LineageCapabilities,
    LineageProviderInfo,
)


class StaticSQLAdapter(BaseLineageAdapter):
    """Static SQL analysis adapter.

    Config:
        sql_files: List of SQL file paths to analyze
        sql_directory: Directory containing SQL files
        git_repo_url: Optional GitHub repo URL for source links

    Parses CREATE TABLE, INSERT, SELECT statements to infer lineage.
    """

    def __init__(
        self,
        sql_files: list[str] | None = None,
        sql_directory: str | None = None,
        git_repo_url: str | None = None,
        dialect: str = "snowflake",
        **kwargs,
    ):
        self._sql_files = sql_files or []
        self._sql_directory = sql_directory
        self._git_repo_url = git_repo_url
        self._dialect = dialect
        self._parser = SQLLineageParser(dialect=dialect)

        # Cached lineage graph
        self._lineage: dict[str, list[str]] | None = None
        self._reverse_lineage: dict[str, list[str]] | None = None

    @property
    def capabilities(self) -> LineageCapabilities:
        return LineageCapabilities(
            supports_column_lineage=True,   # sqlglot can do column lineage
            supports_job_runs=False,        # No runtime info
            supports_freshness=False,
            supports_search=True,
            supports_owners=False,
            supports_tags=False,
            is_realtime=False,
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        return LineageProviderInfo(
            provider="static_sql",
            display_name="SQL Analysis",
            description="Lineage inferred from SQL file analysis",
            capabilities=self.capabilities,
        )

    async def _ensure_parsed(self) -> None:
        """Parse all SQL files if not already done."""
        if self._lineage is not None:
            return

        self._lineage = {}
        self._reverse_lineage = {}

        sql_files = self._collect_sql_files()

        for file_path in sql_files:
            with open(file_path) as f:
                sql = f.read()

            # Parse lineage from SQL
            parsed = self._parser.parse(sql)

            for output_table in parsed.outputs:
                self._lineage[output_table] = parsed.inputs
                for input_table in parsed.inputs:
                    self._reverse_lineage.setdefault(input_table, []).append(output_table)

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get upstream tables from parsed SQL."""
        await self._ensure_parsed()

        upstream = []
        visited = set()

        def traverse(table: str, current_depth: int):
            if current_depth > depth or table in visited:
                return
            visited.add(table)

            for parent in self._lineage.get(table, []):
                if parent not in visited:
                    upstream.append(self._table_to_dataset(parent))
                    traverse(parent, current_depth + 1)

        traverse(dataset_id.name, 1)
        return upstream

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Get downstream tables from parsed SQL."""
        await self._ensure_parsed()

        downstream = []
        visited = set()

        def traverse(table: str, current_depth: int):
            if current_depth > depth or table in visited:
                return
            visited.add(table)

            for child in self._reverse_lineage.get(table, []):
                if child not in visited:
                    downstream.append(self._table_to_dataset(child))
                    traverse(child, current_depth + 1)

        traverse(dataset_id.name, 1)
        return downstream

    def _table_to_dataset(self, table_name: str) -> Dataset:
        """Convert table name to Dataset."""
        parts = table_name.split(".")
        return Dataset(
            id=DatasetId(platform="sql", name=table_name),
            name=parts[-1],
            qualified_name=table_name,
            dataset_type=DatasetType.TABLE,
            platform="sql",
            database=parts[0] if len(parts) > 2 else None,
            schema=parts[1] if len(parts) > 2 else (parts[0] if len(parts) > 1 else None),
        )

    def _collect_sql_files(self) -> list[str]:
        """Collect all SQL files to analyze."""
        from pathlib import Path

        files = list(self._sql_files)

        if self._sql_directory:
            sql_dir = Path(self._sql_directory)
            files.extend(str(p) for p in sql_dir.rglob("*.sql"))

        return files
```

---

## 14. Composite Adapter

```python
# backend/src/datadr/lineage/adapters/composite.py

"""Composite lineage adapter.

Merges lineage from multiple sources.
Example: dbt for model lineage + Airflow for orchestration lineage.
"""

from datadr.lineage.adapters.base import BaseLineageAdapter
from datadr.lineage.protocols import LineageAdapter
from datadr.lineage.types import (
    Dataset,
    DatasetId,
    Job,
    JobRun,
    LineageCapabilities,
    LineageGraph,
    LineageProviderInfo,
)


class CompositeLineageAdapter(BaseLineageAdapter):
    """Merges lineage from multiple adapters.

    Config:
        adapters: List of (adapter, priority) tuples

    Higher priority adapters' data takes precedence in conflicts.
    """

    def __init__(
        self,
        adapters: list[tuple[LineageAdapter, int]],
        **kwargs,
    ):
        # Sort by priority (highest first)
        self._adapters = sorted(adapters, key=lambda x: x[1], reverse=True)

    @property
    def capabilities(self) -> LineageCapabilities:
        # Union of all adapter capabilities
        return LineageCapabilities(
            supports_column_lineage=any(a.capabilities.supports_column_lineage for a, _ in self._adapters),
            supports_job_runs=any(a.capabilities.supports_job_runs for a, _ in self._adapters),
            supports_freshness=any(a.capabilities.supports_freshness for a, _ in self._adapters),
            supports_search=any(a.capabilities.supports_search for a, _ in self._adapters),
            supports_owners=any(a.capabilities.supports_owners for a, _ in self._adapters),
            supports_tags=any(a.capabilities.supports_tags for a, _ in self._adapters),
            is_realtime=any(a.capabilities.is_realtime for a, _ in self._adapters),
        )

    @property
    def provider_info(self) -> LineageProviderInfo:
        providers = [a.provider_info.provider for a, _ in self._adapters]
        return LineageProviderInfo(
            provider="composite",
            display_name=f"Composite ({', '.join(providers)})",
            description="Merged lineage from multiple sources",
            capabilities=self.capabilities,
        )

    async def get_dataset(self, dataset_id: DatasetId) -> Dataset | None:
        """Get dataset from first adapter that has it."""
        for adapter, _ in self._adapters:
            result = await adapter.get_dataset(dataset_id)
            if result:
                return result
        return None

    async def get_upstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Merge upstream from all adapters."""
        all_upstream: dict[str, Dataset] = {}

        for adapter, _ in self._adapters:
            try:
                upstream = await adapter.get_upstream(dataset_id, depth)
                for ds in upstream:
                    # First adapter wins (highest priority)
                    if str(ds.id) not in all_upstream:
                        all_upstream[str(ds.id)] = ds
            except Exception:
                continue  # Skip failing adapters

        return list(all_upstream.values())

    async def get_downstream(
        self,
        dataset_id: DatasetId,
        depth: int = 1,
    ) -> list[Dataset]:
        """Merge downstream from all adapters."""
        all_downstream: dict[str, Dataset] = {}

        for adapter, _ in self._adapters:
            try:
                downstream = await adapter.get_downstream(dataset_id, depth)
                for ds in downstream:
                    if str(ds.id) not in all_downstream:
                        all_downstream[str(ds.id)] = ds
            except Exception:
                continue

        return list(all_downstream.values())

    async def get_producing_job(self, dataset_id: DatasetId) -> Job | None:
        """Get producing job from first adapter that has it."""
        for adapter, _ in self._adapters:
            try:
                job = await adapter.get_producing_job(dataset_id)
                if job:
                    return job
            except Exception:
                continue
        return None

    async def get_recent_runs(self, job_id: str, limit: int = 10) -> list[JobRun]:
        """Get runs from adapter that knows about this job."""
        for adapter, _ in self._adapters:
            try:
                runs = await adapter.get_recent_runs(job_id, limit)
                if runs:
                    return runs
            except Exception:
                continue
        return []
```

---

## 15. Lineage Registry

```python
# backend/src/datadr/lineage/registry.py

"""Lineage adapter registry."""

from typing import Any, Type

from datadr.lineage.protocols import LineageAdapter
from datadr.lineage.adapters.dbt import DbtAdapter
from datadr.lineage.adapters.openlineage import OpenLineageAdapter
from datadr.lineage.adapters.airflow import AirflowAdapter
from datadr.lineage.adapters.dagster import DagsterAdapter
from datadr.lineage.adapters.datahub import DataHubAdapter
from datadr.lineage.adapters.static_sql import StaticSQLAdapter
from datadr.lineage.adapters.composite import CompositeLineageAdapter


class LineageRegistry:
    """Registry for lineage adapters."""

    _adapters: dict[str, Type[LineageAdapter]] = {}
    _config_schemas: dict[str, dict[str, Any]] = {}

    @classmethod
    def register(
        cls,
        provider: str,
        adapter_cls: Type[LineageAdapter],
        config_schema: dict[str, Any],
    ) -> None:
        """Register a lineage adapter."""
        cls._adapters[provider] = adapter_cls
        cls._config_schemas[provider] = config_schema

    @classmethod
    def create(cls, provider: str, config: dict[str, Any]) -> LineageAdapter:
        """Create a lineage adapter instance."""
        adapter_cls = cls._adapters.get(provider)
        if not adapter_cls:
            raise ValueError(f"Unknown lineage provider: {provider}")
        return adapter_cls(**config)

    @classmethod
    def create_composite(
        cls,
        configs: list[dict[str, Any]],
    ) -> LineageAdapter:
        """Create composite adapter from multiple configs.

        Each config should have 'provider', 'priority', and provider-specific fields.
        """
        adapters = []
        for config in configs:
            provider = config.pop("provider")
            priority = config.pop("priority", 0)
            adapter = cls.create(provider, config)
            adapters.append((adapter, priority))

        return CompositeLineageAdapter(adapters=adapters)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List registered providers."""
        return list(cls._adapters.keys())

    @classmethod
    def get_config_schema(cls, provider: str) -> dict[str, Any]:
        """Get config schema for provider."""
        return cls._config_schemas.get(provider, {})


# Register built-in adapters
LineageRegistry.register("dbt", DbtAdapter, {
    "display_name": "dbt",
    "description": "Lineage from dbt manifest.json or dbt Cloud",
    "fields": [
        {"name": "manifest_path", "type": "string", "required": False, "group": "local"},
        {"name": "account_id", "type": "string", "required": False, "group": "cloud"},
        {"name": "project_id", "type": "string", "required": False, "group": "cloud"},
        {"name": "api_key", "type": "secret", "required": False, "group": "cloud"},
        {"name": "target_platform", "type": "string", "required": True, "default": "snowflake"},
    ],
})

LineageRegistry.register("openlineage", OpenLineageAdapter, {
    "display_name": "OpenLineage (Marquez)",
    "description": "Runtime lineage from Spark, Airflow, dbt",
    "fields": [
        {"name": "base_url", "type": "string", "required": True, "placeholder": "http://localhost:5000"},
        {"name": "namespace", "type": "string", "required": True, "default": "default"},
        {"name": "api_key", "type": "secret", "required": False},
    ],
})

LineageRegistry.register("airflow", AirflowAdapter, {
    "display_name": "Apache Airflow",
    "description": "Lineage from Airflow DAGs",
    "fields": [
        {"name": "base_url", "type": "string", "required": True},
        {"name": "username", "type": "string", "required": True},
        {"name": "password", "type": "secret", "required": True},
    ],
})

LineageRegistry.register("dagster", DagsterAdapter, {
    "display_name": "Dagster",
    "description": "Asset lineage from Dagster",
    "fields": [
        {"name": "base_url", "type": "string", "required": True},
        {"name": "api_token", "type": "secret", "required": False},
    ],
})

LineageRegistry.register("datahub", DataHubAdapter, {
    "display_name": "DataHub",
    "description": "Lineage from DataHub metadata platform",
    "fields": [
        {"name": "base_url", "type": "string", "required": True},
        {"name": "token", "type": "secret", "required": True},
    ],
})

LineageRegistry.register("static_sql", StaticSQLAdapter, {
    "display_name": "SQL Analysis",
    "description": "Infer lineage by parsing SQL files",
    "fields": [
        {"name": "sql_directory", "type": "string", "required": False},
        {"name": "git_repo_url", "type": "string", "required": False},
        {"name": "dialect", "type": "enum", "required": True, "default": "snowflake", "options": [
            {"value": "snowflake", "label": "Snowflake"},
            {"value": "postgres", "label": "PostgreSQL"},
            {"value": "bigquery", "label": "BigQuery"},
            {"value": "redshift", "label": "Redshift"},
        ]},
    ],
})
```

---

## 16. API Endpoints

```python
# backend/src/datadr/api/routes/lineage.py

"""Lineage API endpoints."""

from fastapi import APIRouter, Depends, Query

from datadr.lineage.registry import LineageRegistry
from datadr.lineage.types import DatasetId

router = APIRouter(prefix="/lineage", tags=["lineage"])


@router.get("/providers")
async def list_providers():
    """List available lineage providers."""
    providers = []
    for provider in LineageRegistry.list_providers():
        schema = LineageRegistry.get_config_schema(provider)
        providers.append({"id": provider, **schema})
    return {"providers": providers}


@router.get("/upstream")
async def get_upstream(
    platform: str,
    dataset: str,
    depth: int = Query(default=1, ge=1, le=10),
    lineage_adapter = Depends(get_lineage_adapter),
):
    """Get upstream datasets."""
    dataset_id = DatasetId(platform=platform, name=dataset)
    upstream = await lineage_adapter.get_upstream(dataset_id, depth=depth)
    return {"upstream": [ds.__dict__ for ds in upstream]}


@router.get("/downstream")
async def get_downstream(
    platform: str,
    dataset: str,
    depth: int = Query(default=1, ge=1, le=10),
    lineage_adapter = Depends(get_lineage_adapter),
):
    """Get downstream datasets."""
    dataset_id = DatasetId(platform=platform, name=dataset)
    downstream = await lineage_adapter.get_downstream(dataset_id, depth=depth)
    return {"downstream": [ds.__dict__ for ds in downstream]}


@router.get("/graph")
async def get_lineage_graph(
    platform: str,
    dataset: str,
    upstream_depth: int = Query(default=3, ge=0, le=10),
    downstream_depth: int = Query(default=3, ge=0, le=10),
    lineage_adapter = Depends(get_lineage_adapter),
):
    """Get full lineage graph."""
    dataset_id = DatasetId(platform=platform, name=dataset)
    graph = await lineage_adapter.get_lineage_graph(
        dataset_id,
        upstream_depth=upstream_depth,
        downstream_depth=downstream_depth,
    )
    return graph.to_dict()


@router.get("/job/{job_id}/runs")
async def get_job_runs(
    job_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    lineage_adapter = Depends(get_lineage_adapter),
):
    """Get recent runs of a job."""
    runs = await lineage_adapter.get_recent_runs(job_id, limit=limit)
    return {"runs": [r.__dict__ for r in runs]}


@router.get("/search")
async def search_datasets(
    q: str,
    limit: int = Query(default=20, ge=1, le=100),
    lineage_adapter = Depends(get_lineage_adapter),
):
    """Search for datasets."""
    datasets = await lineage_adapter.search_datasets(q, limit=limit)
    return {"datasets": [ds.__dict__ for ds in datasets]}
```

---

## 17. Usage in Investigation Engine

```python
# How the investigation engine uses lineage

from datadr.lineage.registry import LineageRegistry
from datadr.lineage.types import DatasetId

class InvestigationEngine:
    """Data quality investigation engine."""

    def __init__(
        self,
        llm_adapter,
        data_adapter,
        lineage_adapter,  # Optional
    ):
        self._llm = llm_adapter
        self._data = data_adapter
        self._lineage = lineage_adapter

    async def investigate(self, table: str) -> InvestigationResult:
        """Run investigation with lineage context."""

        # Get schema
        schema = await self._data.get_schema()

        # Get lineage context (if available)
        lineage_context = ""
        if self._lineage:
            dataset_id = DatasetId(
                platform=self._data.model_info.provider,
                name=table,
            )

            # Get upstream - potential root causes
            upstream = await self._lineage.get_upstream(dataset_id, depth=2)

            # Get producing job - when did it last run?
            job = await self._lineage.get_producing_job(dataset_id)

            lineage_context = f"""
## Lineage Context

### Upstream Tables (potential root causes)
{self._format_upstream(upstream)}

### Producing Job
{self._format_job(job)}
"""

        # Build prompt with lineage context
        messages = [
            Message(role=Role.SYSTEM, content=SYSTEM_PROMPT),
            Message(role=Role.USER, content=f"""
Investigate data quality issues in table '{table}'.

{schema_context}
{lineage_context}

If you find issues, trace them to potential root causes using the lineage.
"""),
        ]

        response = await self._llm.complete(messages, tools=TOOLS)
        ...

    def _format_upstream(self, upstream: list[Dataset]) -> str:
        """Format upstream datasets for prompt."""
        if not upstream:
            return "No upstream tables found."

        lines = []
        for ds in upstream:
            lines.append(f"- {ds.qualified_name}")
            if ds.source_code_path:
                lines.append(f"  Code: {ds.source_code_path}")
        return "\n".join(lines)

    def _format_job(self, job: Job | None) -> str:
        """Format producing job for prompt."""
        if not job:
            return "No producing job found."

        return f"""
- Job: {job.name}
- Type: {job.job_type.value}
- Code: {job.source_code_path or 'Unknown'}
"""
```

---

## 18. Implementation Checklist

### Phase 1: Core Infrastructure (Days 1-2)

- [ ] Create `lineage/types.py` with all unified types
- [ ] Create `lineage/protocols.py` with LineageAdapter protocol
- [ ] Create `lineage/exceptions.py`
- [ ] Create `lineage/adapters/base.py`
- [ ] Create `lineage/registry.py`
- [ ] Create `lineage/graph.py` with traversal utilities

### Phase 2: dbt Adapter (Days 2-3)

- [ ] Implement `DbtAdapter` for manifest.json
- [ ] Add dbt Cloud API support
- [ ] Test with real dbt project
- [ ] Handle column lineage from catalog.json

### Phase 3: OpenLineage Adapter (Days 3-4)

- [ ] Implement `OpenLineageAdapter` for Marquez
- [ ] Test with Marquez instance
- [ ] Handle lineage graph response format

### Phase 4: Airflow & Dagster (Days 4-5)

- [ ] Implement `AirflowAdapter`
- [ ] Implement `DagsterAdapter`
- [ ] Test with real instances

### Phase 5: DataHub Adapter (Day 5-6)

- [ ] Implement `DataHubAdapter`
- [ ] Handle GraphQL queries
- [ ] Test column lineage

### Phase 6: Static SQL & Composite (Days 6-7)

- [ ] Implement `StaticSQLAdapter` with sqlglot
- [ ] Implement `CompositeLineageAdapter`
- [ ] Test merging from multiple sources

### Phase 7: Integration (Days 7-8)

- [ ] Add API endpoints
- [ ] Integrate with InvestigationEngine
- [ ] Add to tenant configuration
- [ ] End-to-end testing
