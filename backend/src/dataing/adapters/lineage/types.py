"""Unified types for lineage information.

These types normalize the differences between lineage providers.
All adapters convert to/from these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DatasetType(str, Enum):
    """Type of dataset."""

    TABLE = "table"
    VIEW = "view"
    EXTERNAL = "external"
    SEED = "seed"
    SOURCE = "source"
    MODEL = "model"
    SNAPSHOT = "snapshot"
    FILE = "file"
    STREAM = "stream"
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


class LineageProviderType(str, Enum):
    """Types of lineage providers."""

    DBT = "dbt"
    OPENLINEAGE = "openlineage"
    AIRFLOW = "airflow"
    DAGSTER = "dagster"
    DATAHUB = "datahub"
    OPENMETADATA = "openmetadata"
    ATLAN = "atlan"
    STATIC_SQL = "static_sql"
    COMPOSITE = "composite"


@dataclass(frozen=True)
class DatasetId:
    """Unique identifier for a dataset.

    Uses a URN-like format for consistency across providers.

    Attributes:
        platform: The data platform (e.g., "snowflake", "postgres", "s3").
        name: Fully qualified name (e.g., "database.schema.table").
    """

    platform: str
    name: str

    def __str__(self) -> str:
        """Return URN-like string representation."""
        return f"{self.platform}://{self.name}"

    @classmethod
    def from_urn(cls, urn: str) -> DatasetId:
        """Parse from URN string.

        Handles formats:
        - "snowflake://db.schema.table"
        - "urn:li:dataset:(urn:li:dataPlatform:snowflake,db.schema.table,PROD)"

        Args:
            urn: URN string to parse.

        Returns:
            DatasetId instance.
        """
        if urn.startswith("urn:li:dataset:"):
            # DataHub format
            parts = urn.split(",")
            platform = parts[0].split(":")[-1]
            name = parts[1] if len(parts) > 1 else ""
            return cls(platform=platform, name=name)
        elif "://" in urn:
            # Simple format
            platform, name = urn.split("://", 1)
            return cls(platform=platform, name=name)
        else:
            return cls(platform="unknown", name=urn)


@dataclass
class Dataset:
    """A dataset (table, view, file, etc.) in the lineage graph.

    Attributes:
        id: Unique identifier for the dataset.
        name: Short name (e.g., "orders").
        qualified_name: Full name (e.g., "analytics.public.orders").
        dataset_type: Type of dataset.
        platform: Data platform.
        database: Database name (optional).
        schema: Schema name (optional).
        description: Human-readable description.
        tags: List of tags.
        owners: List of owner identifiers.
        source_code_url: URL to producing code (e.g., GitHub).
        source_code_path: Relative path in repo.
        last_modified: Last modification timestamp.
        row_count: Approximate row count.
        extra: Provider-specific metadata.
    """

    id: DatasetId
    name: str
    qualified_name: str
    dataset_type: DatasetType
    platform: str
    database: str | None = None
    schema: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    source_code_url: str | None = None
    source_code_path: str | None = None
    last_modified: datetime | None = None
    row_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Column:
    """A column within a dataset.

    Attributes:
        name: Column name.
        data_type: Data type string.
        description: Column description.
        is_primary_key: Whether this is a primary key.
        tags: List of tags.
    """

    name: str
    data_type: str
    description: str | None = None
    is_primary_key: bool = False
    tags: list[str] = field(default_factory=list)


@dataclass
class ColumnLineage:
    """Lineage for a specific column.

    Attributes:
        target_dataset: Target dataset ID.
        target_column: Target column name.
        source_dataset: Source dataset ID.
        source_column: Source column name.
        transformation: SQL expression if known.
        confidence: Confidence score (1.0 = certain, <1.0 = inferred).
    """

    target_dataset: DatasetId
    target_column: str
    source_dataset: DatasetId
    source_column: str
    transformation: str | None = None
    confidence: float = 1.0


@dataclass
class Job:
    """A job/process that produces or consumes datasets.

    Attributes:
        id: Unique job identifier.
        name: Job name.
        job_type: Type of job.
        inputs: List of input dataset IDs.
        outputs: List of output dataset IDs.
        source_code_url: URL to source code.
        source_code_path: Path to source code.
        schedule: Cron expression if scheduled.
        owners: List of owner identifiers.
        tags: List of tags.
        extra: Provider-specific metadata.
    """

    id: str
    name: str
    job_type: JobType
    inputs: list[DatasetId] = field(default_factory=list)
    outputs: list[DatasetId] = field(default_factory=list)
    source_code_url: str | None = None
    source_code_path: str | None = None
    schedule: str | None = None
    owners: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobRun:
    """A single execution of a job.

    Attributes:
        id: Run identifier.
        job_id: Parent job identifier.
        status: Run status.
        started_at: Start timestamp.
        ended_at: End timestamp.
        duration_seconds: Duration in seconds.
        inputs: Datasets read during this run.
        outputs: Datasets written during this run.
        error_message: Error message if failed.
        logs_url: URL to logs.
        extra: Provider-specific metadata.
    """

    id: str
    job_id: str
    status: RunStatus
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    inputs: list[DatasetId] = field(default_factory=list)
    outputs: list[DatasetId] = field(default_factory=list)
    error_message: str | None = None
    logs_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageEdge:
    """An edge in the lineage graph.

    Attributes:
        source: Source dataset ID.
        target: Target dataset ID.
        job: Job that creates this edge (optional).
        edge_type: Type of edge ("transforms", "copies", "derives").
        column_lineage: Column-level lineage (if available).
    """

    source: DatasetId
    target: DatasetId
    job: Job | None = None
    edge_type: str = "transforms"
    column_lineage: list[ColumnLineage] = field(default_factory=list)


@dataclass
class LineageGraph:
    """A lineage graph centered on a dataset.

    Attributes:
        root: The root dataset ID.
        datasets: Map of dataset ID string to Dataset.
        edges: List of lineage edges.
        jobs: Map of job ID to Job.
    """

    root: DatasetId
    datasets: dict[str, Dataset] = field(default_factory=dict)
    edges: list[LineageEdge] = field(default_factory=list)
    jobs: dict[str, Job] = field(default_factory=dict)

    def get_upstream(self, dataset_id: DatasetId, depth: int = 1) -> list[Dataset]:
        """Get datasets upstream of the given dataset.

        Args:
            dataset_id: Dataset to find upstream for.
            depth: How many levels to traverse.

        Returns:
            List of upstream datasets.
        """
        upstream: list[Dataset] = []
        visited: set[str] = set()
        current_level = [dataset_id]

        for _ in range(depth):
            next_level: list[DatasetId] = []
            for ds_id in current_level:
                for edge in self.edges:
                    if str(edge.target) == str(ds_id) and str(edge.source) not in visited:
                        visited.add(str(edge.source))
                        if str(edge.source) in self.datasets:
                            upstream.append(self.datasets[str(edge.source)])
                        next_level.append(edge.source)
            current_level = next_level

        return upstream

    def get_downstream(self, dataset_id: DatasetId, depth: int = 1) -> list[Dataset]:
        """Get datasets downstream of the given dataset.

        Args:
            dataset_id: Dataset to find downstream for.
            depth: How many levels to traverse.

        Returns:
            List of downstream datasets.
        """
        downstream: list[Dataset] = []
        visited: set[str] = set()
        current_level = [dataset_id]

        for _ in range(depth):
            next_level: list[DatasetId] = []
            for ds_id in current_level:
                for edge in self.edges:
                    if str(edge.source) == str(ds_id) and str(edge.target) not in visited:
                        visited.add(str(edge.target))
                        if str(edge.target) in self.datasets:
                            downstream.append(self.datasets[str(edge.target)])
                        next_level.append(edge.target)
            current_level = next_level

        return downstream

    def get_path(self, source: DatasetId, target: DatasetId) -> list[LineageEdge] | None:
        """Find path between two datasets using BFS.

        Args:
            source: Source dataset.
            target: Target dataset.

        Returns:
            List of edges forming the path, or None if no path exists.
        """
        from collections import deque

        if str(source) == str(target):
            return []

        # Build adjacency list
        adj: dict[str, list[LineageEdge]] = {}
        for edge in self.edges:
            adj.setdefault(str(edge.source), []).append(edge)

        # BFS
        queue: deque[tuple[str, list[LineageEdge]]] = deque()
        queue.append((str(source), []))
        visited = {str(source)}

        while queue:
            current, path = queue.popleft()
            for edge in adj.get(current, []):
                if str(edge.target) == str(target):
                    return path + [edge]
                if str(edge.target) not in visited:
                    visited.add(str(edge.target))
                    queue.append((str(edge.target), path + [edge]))

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict for API responses.

        Returns:
            Dictionary representation of the graph.
        """
        return {
            "root": str(self.root),
            "datasets": {
                k: {
                    "id": str(v.id),
                    "name": v.name,
                    "qualified_name": v.qualified_name,
                    "dataset_type": v.dataset_type.value,
                    "platform": v.platform,
                    "database": v.database,
                    "schema": v.schema,
                    "description": v.description,
                    "tags": v.tags,
                    "owners": v.owners,
                }
                for k, v in self.datasets.items()
            },
            "edges": [
                {
                    "source": str(e.source),
                    "target": str(e.target),
                    "edge_type": e.edge_type,
                    "job_id": e.job.id if e.job else None,
                }
                for e in self.edges
            ],
            "jobs": {
                k: {
                    "id": v.id,
                    "name": v.name,
                    "job_type": v.job_type.value,
                    "inputs": [str(i) for i in v.inputs],
                    "outputs": [str(o) for o in v.outputs],
                }
                for k, v in self.jobs.items()
            },
        }


@dataclass(frozen=True)
class LineageCapabilities:
    """What this lineage provider can do.

    Attributes:
        supports_column_lineage: Whether column-level lineage is supported.
        supports_job_runs: Whether job run history is available.
        supports_freshness: Whether freshness information is available.
        supports_search: Whether dataset search is supported.
        supports_owners: Whether owner information is available.
        supports_tags: Whether tags are available.
        max_upstream_depth: Maximum upstream traversal depth.
        max_downstream_depth: Maximum downstream traversal depth.
        is_realtime: Whether lineage updates in real-time.
    """

    supports_column_lineage: bool = False
    supports_job_runs: bool = False
    supports_freshness: bool = False
    supports_search: bool = False
    supports_owners: bool = False
    supports_tags: bool = False
    max_upstream_depth: int | None = None
    max_downstream_depth: int | None = None
    is_realtime: bool = False


@dataclass(frozen=True)
class LineageProviderInfo:
    """Information about a lineage provider.

    Attributes:
        provider: Provider type.
        display_name: Human-readable name.
        description: Description of the provider.
        capabilities: Provider capabilities.
    """

    provider: LineageProviderType
    display_name: str
    description: str
    capabilities: LineageCapabilities
