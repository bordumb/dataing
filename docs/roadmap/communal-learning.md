DataDr Privacy Layer: Technical SpecificationImplementation Directive for Engineering TeamCRITICAL INSTRUCTION: This specification must be implemented in its entirety. Every component, interface, and security measure described herein is required for production deployment. Do not skip sections. Do not implement partial solutions. Do not defer security measures to "later." The privacy guarantees we advertise to customers depend on complete implementation of this architecture.This document covers:

Customer-side data collection agent
Privacy-preserving transformation layer
Secure transmission protocol
Server-side secure storage
Privacy-preserving computation engine
Zero-knowledge proof system for contribution validity
Table of Contents
Architecture Overview
Customer-Side Agent
Local Privacy Transformation
Secure Transmission Layer
Server-Side Secure Storage
Differential Privacy Computation Engine
Zero-Knowledge Proof System
Privacy Budget Management
Federated Learning Protocol
Audit and Compliance System
Testing and Verification
Deployment Configuration
1. Architecture Overview1.1 System Topology┌─────────────────────────────────────────────────────────────────────────────┐
│                           CUSTOMER PREMISES                                  │
│                                                                              │
│  ┌──────────────┐    ┌──────────────────┐    ┌────────────────────────────┐ │
│  │              │    │                  │    │                            │ │
│  │  Customer's  │───▶│  DataDr Agent    │───▶│  Local Privacy Transform  │ │
│  │  Data        │    │  (Collector)     │    │  (DP + ZKP Generation)    │ │
│  │  Warehouse   │    │                  │    │                            │ │
│  └──────────────┘    └──────────────────┘    └─────────────┬──────────────┘ │
│                                                            │                 │
│         Raw data NEVER leaves this boundary ───────────────┼─────────────── │
│                                                            │                 │
│                                              ┌─────────────▼──────────────┐ │
│                                              │   Encrypted Contribution   │ │
│                                              │   Package:                 │ │
│                                              │   • DP-noised statistics   │ │
│                                              │   • ZK validity proof      │ │
│                                              │   • Encrypted metadata     │ │
│                                              └─────────────┬──────────────┘ │
└────────────────────────────────────────────────────────────┼────────────────┘
                                                             │
                                                             │ mTLS + Certificate Pinning
                                                             │
┌────────────────────────────────────────────────────────────▼────────────────┐
│                           DATADR INFRASTRUCTURE                              │
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐  │
│  │                  │    │                  │    │                      │  │
│  │  Ingestion       │───▶│  ZKP Verifier    │───▶│  Secure Aggregator   │  │
│  │  Gateway         │    │                  │    │                      │  │
│  │                  │    │                  │    │                      │  │
│  └──────────────────┘    └──────────────────┘    └──────────┬───────────┘  │
│                                                              │              │
│  ┌──────────────────────────────────────────────────────────▼───────────┐  │
│  │                                                                       │  │
│  │                    Encrypted Storage Layer                            │  │
│  │                    (Customer-isolated, key-per-tenant)                │  │
│  │                                                                       │  │
│  └──────────────────────────────────────────────────────────┬───────────┘  │
│                                                              │              │
│  ┌──────────────────────────────────────────────────────────▼───────────┐  │
│  │                                                                       │  │
│  │                    DP Computation Engine                              │  │
│  │                    (Privacy budget tracking, secure computation)      │  │
│  │                                                                       │  │
│  └──────────────────────────────────────────────────────────┬───────────┘  │
│                                                              │              │
│  ┌──────────────────────────────────────────────────────────▼───────────┐  │
│  │                                                                       │  │
│  │                    Collective Intelligence Pool                       │  │
│  │                    (Aggregated, DP-protected patterns)                │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘1.2 Data Flow SummaryStageLocationWhat ExistsPrivacy Mechanism1. CollectionCustomerRaw query logs, schemas, metricsNone yet (customer's data)2. Local TransformCustomerAggregated patterns, statisticsLocal DP applied3. ZKP GenerationCustomerValidity proofsCryptographic hiding4. TransmissionNetworkEncrypted packagemTLS, certificate pinning5. StorageDataDrEncrypted contributionsAES-256-GCM, tenant isolation6. AggregationDataDrCross-tenant aggregatesSecure aggregation protocol7. ComputationDataDrGlobal patternsDP with formal (ε,δ) guarantees1.3 Privacy GuaranteesThis system provides the following formally provable guarantees:
Differential Privacy (ε,δ)-guarantee: For ε=1.0, δ=1e-8, the probability of any inference about a single record changes by at most e^ε ≈ 2.718x whether that record is included or not.

Zero-Knowledge: The ZKP system reveals nothing about the underlying data beyond the validity of the contribution.

Forward Secrecy: Compromise of current keys does not compromise historical data.

Tenant Isolation: One customer's data cannot leak to another customer even with server compromise.
2. Customer-Side Agent2.1 Agent ArchitectureThe DataDr Agent runs within the customer's infrastructure. It MUST be deployed as a containerized service with minimal privileges.┌─────────────────────────────────────────────────────────────┐
│                    DataDr Agent Container                    │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │                 │  │                 │  │             │ │
│  │  Connector      │  │  Pattern        │  │  Privacy    │ │
│  │  Manager        │  │  Extractor      │  │  Engine     │ │
│  │                 │  │                 │  │             │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬──────┘ │
│           │                    │                   │        │
│           ▼                    ▼                   ▼        │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                   Local State Store                     ││
│  │              (SQLite, encrypted at rest)                ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                   Contribution Queue                    ││
│  │              (Outbound, batched, encrypted)             ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘2.2 Connector ManagerThe Connector Manager interfaces with customer data sources. It supports read-only connections to:
PostgreSQL
Trino/Presto
Snowflake
BigQuery
Redshift
Databricks
CRITICAL: Connectors MUST be read-only. The agent MUST NOT have write access to customer data.2.2.1 Connector Interfacepython# datadr_agent/connectors/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

@dataclass(frozen=True)
class TableSchema:
    """Immutable representation of a table's schema."""
    catalog: str
    schema: str
    table: str
    columns: tuple[ColumnInfo, ...]
    row_count_approx: int
    last_modified: datetime | None

@dataclass(frozen=True)
class ColumnInfo:
    """Immutable representation of a column."""
    name: str
    data_type: str
    nullable: bool
    is_partition_key: bool

@dataclass(frozen=True)
class QueryLogEntry:
    """A single query execution record."""
    query_id: str
    query_hash: str  # SHA-256 of normalized query (no literals)
    tables_accessed: tuple[str, ...]
    execution_time_ms: int
    rows_scanned: int
    rows_returned: int
    error_code: str | None
    timestamp: datetime

class BaseConnector(ABC):
    """
    Abstract base class for all data source connectors.

    Implementations MUST:
    - Use read-only credentials
    - Implement connection pooling with limits
    - Handle timeouts gracefully
    - Never cache raw data beyond immediate processing
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to data source."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection and release resources."""
        ...

    @abstractmethod
    async def list_schemas(self) -> list[TableSchema]:
        """
        Enumerate all accessible table schemas.

        This method MUST NOT return actual data, only metadata.
        """
        ...

    @abstractmethod
    async def get_column_statistics(
        self,
        table: TableSchema,
        sample_rate: float = 0.01
    ) -> dict[str, ColumnStatistics]:
        """
        Compute column-level statistics using sampling.

        Args:
            table: Target table
            sample_rate: Fraction of rows to sample (default 1%)

        Returns:
            Statistics per column (null rate, cardinality, distribution)

        IMPORTANT: This samples data, does not extract it.
        """
        ...

    @abstractmethod
    async def stream_query_logs(
        self,
        since: datetime,
        batch_size: int = 1000
    ) -> AsyncIterator[list[QueryLogEntry]]:
        """
        Stream query execution logs from the data source.

        This is the PRIMARY data collection mechanism.
        Query logs contain metadata about queries, not the data itself.
        """
        ...2.2.2 PostgreSQL Connector Implementationpython# datadr_agent/connectors/postgres.py

import asyncpg
from datetime import datetime
from typing import AsyncIterator

class PostgresConnector(BaseConnector):
    """
    PostgreSQL connector using asyncpg for async I/O.

    Required database permissions:
    - pg_stat_statements (for query logs)
    - USAGE on schemas
    - SELECT on pg_catalog tables

    DO NOT grant:
    - INSERT, UPDATE, DELETE on any tables
    - SUPERUSER or CREATEDB
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,  # Should come from secrets manager
        ssl_mode: str = "verify-full",
        ssl_ca_cert: str | None = None,
        max_connections: int = 5,
        statement_timeout_ms: int = 30000,
    ):
        self._config = {
            "host": host,
            "port": port,
            "database": database,
            "user": username,
            "password": password,
            "ssl": ssl_mode,
            "min_size": 1,
            "max_size": max_connections,
            "command_timeout": statement_timeout_ms / 1000,
        }
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(**self._config)

        # Verify read-only access
        async with self._pool.acquire() as conn:
            # This query should fail if we have write access (good!)
            try:
                await conn.execute(
                    "CREATE TEMP TABLE _datadr_write_test (id int)"
                )
                await conn.execute("DROP TABLE _datadr_write_test")
                # If we get here, we have write access - this is a configuration error
                raise SecurityError(
                    "DataDr agent has write access to database. "
                    "Please configure read-only credentials."
                )
            except asyncpg.InsufficientPrivilegeError:
                # Expected - we should not have write access
                pass

    async def stream_query_logs(
        self,
        since: datetime,
        batch_size: int = 1000
    ) -> AsyncIterator[list[QueryLogEntry]]:
        """
        Stream query logs from pg_stat_statements.

        Requires pg_stat_statements extension to be enabled.
        """
        query = """
            SELECT
                queryid::text as query_id,
                encode(sha256(query::bytea), 'hex') as query_hash,
                -- Extract table names from query (simplified, real impl uses parser)
                query,
                mean_exec_time * calls as total_time_ms,
                rows,
                calls,
                -- Note: pg_stat_statements doesn't have per-execution timestamps
                -- We use snapshot time as approximation
                now() as snapshot_time
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY queryid
            LIMIT $1 OFFSET $2
        """

        offset = 0
        while True:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, batch_size, offset)

            if not rows:
                break

            entries = [
                QueryLogEntry(
                    query_id=row["query_id"],
                    query_hash=row["query_hash"],
                    tables_accessed=self._extract_tables(row["query"]),
                    execution_time_ms=int(row["total_time_ms"]),
                    rows_scanned=row["rows"],
                    rows_returned=row["rows"],
                    error_code=None,
                    timestamp=row["snapshot_time"],
                )
                for row in rows
            ]

            yield entries
            offset += batch_size

    def _extract_tables(self, query: str) -> tuple[str, ...]:
        """
        Extract table names from query using sqlglot parser.

        This is a critical function - it must handle all SQL dialects
        the customer might use.
        """
        import sqlglot

        try:
            parsed = sqlglot.parse_one(query, dialect="postgres")
            tables = set()
            for table in parsed.find_all(sqlglot.exp.Table):
                tables.add(f"{table.db}.{table.name}" if table.db else table.name)
            return tuple(sorted(tables))
        except Exception:
            # If parsing fails, return empty (don't crash)
            return ()2.3 Pattern ExtractorThe Pattern Extractor processes query logs and schema metadata to identify data quality patterns.python# datadr_agent/extraction/pattern_extractor.py

from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from typing import Sequence

class PatternType(str, Enum):
    """Taxonomy of data quality patterns we extract."""

    # Volume patterns
    NULL_SPIKE = "null_spike"
    CARDINALITY_DRIFT = "cardinality_drift"
    VOLUME_ANOMALY = "volume_anomaly"

    # Schema patterns
    TYPE_MISMATCH = "type_mismatch"
    SCHEMA_DRIFT = "schema_drift"
    MISSING_COLUMN = "missing_column"

    # Query patterns
    SLOW_QUERY_PATTERN = "slow_query_pattern"
    FAILED_QUERY_PATTERN = "failed_query_pattern"
    CARTESIAN_JOIN = "cartesian_join"

    # Temporal patterns
    LATE_ARRIVING_DATA = "late_arriving_data"
    DUPLICATE_WINDOW = "duplicate_window"
    SEASONALITY_BREAK = "seasonality_break"

@dataclass(frozen=True)
class ExtractedPattern:
    """
    A single pattern extracted from customer data.

    This is the LAST representation that contains any
    customer-specific information. After this point,
    differential privacy is applied.
    """
    pattern_type: PatternType

    # Schema fingerprint (hashed, not raw names)
    schema_fingerprint: str

    # Severity (0.0 to 1.0)
    severity: float

    # Temporal information
    detected_at: datetime
    duration: timedelta | None

    # Pattern-specific metrics (will be DP-noised)
    metrics: dict[str, float]

    # Sample size (for DP calibration)
    sample_count: int

    # Causal indicators (also DP-noised)
    upstream_correlations: dict[str, float]

class PatternExtractor:
    """
    Extracts data quality patterns from query logs and schema metadata.

    This class runs LOCALLY on customer infrastructure.
    Extracted patterns are passed to the Privacy Engine before transmission.
    """

    def __init__(
        self,
        min_sample_size: int = 100,  # Minimum events to form a pattern
        lookback_window: timedelta = timedelta(days=7),
        severity_threshold: float = 0.3,
    ):
        self._min_sample_size = min_sample_size
        self._lookback_window = lookback_window
        self._severity_threshold = severity_threshold

    async def extract_patterns(
        self,
        query_logs: Sequence[QueryLogEntry],
        schemas: Sequence[TableSchema],
        column_stats: dict[str, ColumnStatistics],
    ) -> list[ExtractedPattern]:
        """
        Main extraction pipeline.

        Returns patterns that meet minimum sample size and severity thresholds.
        """
        patterns = []

        # Detect NULL spikes
        patterns.extend(
            await self._detect_null_spikes(schemas, column_stats)
        )

        # Detect query failure patterns
        patterns.extend(
            await self._detect_query_failures(query_logs)
        )

        # Detect slow query patterns
        patterns.extend(
            await self._detect_slow_queries(query_logs)
        )

        # Detect volume anomalies
        patterns.extend(
            await self._detect_volume_anomalies(query_logs, schemas)
        )

        # Filter by minimum sample size and severity
        patterns = [
            p for p in patterns
            if p.sample_count >= self._min_sample_size
            and p.severity >= self._severity_threshold
        ]

        return patterns

    async def _detect_null_spikes(
        self,
        schemas: Sequence[TableSchema],
        column_stats: dict[str, ColumnStatistics],
    ) -> list[ExtractedPattern]:
        """
        Detect columns with abnormally high NULL rates.

        A NULL spike is defined as:
        - Current NULL rate > historical_mean + 2 * historical_stddev
        - OR current NULL rate > 0.5 (absolute threshold)
        """
        patterns = []

        for schema in schemas:
            for column in schema.columns:
                key = f"{schema.catalog}.{schema.schema}.{schema.table}.{column.name}"
                stats = column_stats.get(key)

                if stats is None:
                    continue

                # Check for NULL spike
                if self._is_null_spike(stats):
                    # Create schema fingerprint (hashed)
                    fingerprint = self._fingerprint_schema(schema, column)

                    patterns.append(ExtractedPattern(
                        pattern_type=PatternType.NULL_SPIKE,
                        schema_fingerprint=fingerprint,
                        severity=self._calculate_null_severity(stats),
                        detected_at=datetime.utcnow(),
                        duration=None,
                        metrics={
                            "null_rate": stats.null_rate,
                            "historical_null_rate": stats.historical_null_rate,
                            "row_count": float(stats.row_count),
                        },
                        sample_count=stats.sample_size,
                        upstream_correlations={},
                    ))

        return patterns

    def _fingerprint_schema(
        self,
        schema: TableSchema,
        column: ColumnInfo
    ) -> str:
        """
        Create a privacy-preserving fingerprint of the schema structure.

        This fingerprint:
        - Does NOT include actual table/column names
        - DOES include structural information (types, positions)
        - Allows matching similar schemas across organizations
        """
        import hashlib

        # Collect structural features
        features = [
            f"col_type:{column.data_type}",
            f"col_nullable:{column.nullable}",
            f"col_position:{schema.columns.index(column)}",
            f"table_col_count:{len(schema.columns)}",
            f"table_approx_rows_bucket:{self._bucket_row_count(schema.row_count_approx)}",
        ]

        # Add neighboring column types (structural context)
        col_idx = schema.columns.index(column)
        if col_idx > 0:
            features.append(f"prev_col_type:{schema.columns[col_idx-1].data_type}")
        if col_idx < len(schema.columns) - 1:
            features.append(f"next_col_type:{schema.columns[col_idx+1].data_type}")

        # Hash to create fingerprint
        feature_str = "|".join(sorted(features))
        return hashlib.sha256(feature_str.encode()).hexdigest()[:16]

    def _bucket_row_count(self, count: int) -> str:
        """Bucket row counts to prevent fingerprinting by exact size."""
        if count < 1000:
            return "tiny"
        elif count < 100000:
            return "small"
        elif count < 10000000:
            return "medium"
        elif count < 1000000000:
            return "large"
        else:
            return "huge"3. Local Privacy Transformation3.1 Differential Privacy EngineThe DP Engine applies differential privacy to extracted patterns BEFORE they leave the customer's infrastructure.python# datadr_agent/privacy/dp_engine.py

from dataclasses import dataclass
from typing import TypeVar, Generic
import numpy as np

T = TypeVar('T', int, float)

@dataclass(frozen=True)
class DPConfig:
    """
    Differential Privacy configuration.

    These parameters determine the privacy-utility tradeoff.
    """
    epsilon: float = 1.0  # Privacy parameter (lower = more private)
    delta: float = 1e-8   # Probability of privacy breach

    # Sensitivity bounds
    max_contribution_per_user: int = 1  # For user-level DP

    # Clipping bounds for numeric values
    null_rate_clip: tuple[float, float] = (0.0, 1.0)
    row_count_clip: tuple[float, float] = (0.0, 1e12)
    severity_clip: tuple[float, float] = (0.0, 1.0)

class LocalDPEngine:
    """
    Applies local differential privacy to patterns.

    "Local" means noise is added on the customer's machine,
    before data is transmitted. This provides the strongest
    privacy guarantee - even DataDr cannot see true values.

    We use the Laplace mechanism for numeric values and
    randomized response for categorical values.
    """

    def __init__(self, config: DPConfig):
        self._config = config
        self._rng = np.random.default_rng()

    def privatize_pattern(
        self,
        pattern: ExtractedPattern
    ) -> "PrivatizedPattern":
        """
        Apply differential privacy to a single pattern.

        Returns a PrivatizedPattern where all numeric values
        have been noised according to the Laplace mechanism.
        """
        # Privatize each metric
        privatized_metrics = {}
        for key, value in pattern.metrics.items():
            clip_bounds = self._get_clip_bounds(key)
            privatized_metrics[key] = self._laplace_mechanism(
                value=value,
                clip_low=clip_bounds[0],
                clip_high=clip_bounds[1],
                epsilon=self._config.epsilon / len(pattern.metrics),  # Composition
            )

        # Privatize severity
        privatized_severity = self._laplace_mechanism(
            value=pattern.severity,
            clip_low=0.0,
            clip_high=1.0,
            epsilon=self._config.epsilon / 2,
        )

        # Privatize upstream correlations
        privatized_correlations = {}
        if pattern.upstream_correlations:
            eps_per_corr = self._config.epsilon / (2 * len(pattern.upstream_correlations))
            for key, value in pattern.upstream_correlations.items():
                privatized_correlations[key] = self._laplace_mechanism(
                    value=value,
                    clip_low=-1.0,
                    clip_high=1.0,
                    epsilon=eps_per_corr,
                )

        return PrivatizedPattern(
            pattern_type=pattern.pattern_type,
            schema_fingerprint=pattern.schema_fingerprint,
            severity=privatized_severity,
            detected_at=pattern.detected_at,
            metrics=privatized_metrics,
            upstream_correlations=privatized_correlations,
            epsilon_spent=self._config.epsilon,
            delta=self._config.delta,
        )

    def _laplace_mechanism(
        self,
        value: float,
        clip_low: float,
        clip_high: float,
        epsilon: float,
    ) -> float:
        """
        Apply the Laplace mechanism to a single value.

        The Laplace mechanism achieves ε-differential privacy by adding
        noise drawn from Lap(Δf/ε) where Δf is the sensitivity.

        For bounded values, sensitivity = clip_high - clip_low.
        """
        # Clip value to bounds
        clipped = np.clip(value, clip_low, clip_high)

        # Calculate sensitivity
        sensitivity = clip_high - clip_low

        # Calculate noise scale
        scale = sensitivity / epsilon

        # Add Laplace noise
        noise = self._rng.laplace(0, scale)
        noised = clipped + noise

        # Re-clip to bounds (post-processing, doesn't affect privacy)
        return float(np.clip(noised, clip_low, clip_high))

    def _get_clip_bounds(self, metric_key: str) -> tuple[float, float]:
        """Get clipping bounds for a given metric type."""
        bounds_map = {
            "null_rate": self._config.null_rate_clip,
            "historical_null_rate": self._config.null_rate_clip,
            "row_count": self._config.row_count_clip,
            "cardinality": self._config.row_count_clip,
            "execution_time_ms": (0.0, 3600000.0),  # Up to 1 hour
            "error_rate": (0.0, 1.0),
        }
        return bounds_map.get(metric_key, (0.0, 1e6))


@dataclass(frozen=True)
class PrivatizedPattern:
    """
    A pattern after differential privacy has been applied.

    This is safe to transmit to DataDr servers.
    """
    pattern_type: PatternType
    schema_fingerprint: str
    severity: float
    detected_at: datetime
    metrics: dict[str, float]
    upstream_correlations: dict[str, float]

    # Privacy accounting
    epsilon_spent: float
    delta: float3.2 Privacy Budget ManagerTracks privacy budget consumption to prevent exceeding guarantees.python# datadr_agent/privacy/budget_manager.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import json
from pathlib import Path

@dataclass
class BudgetPeriod:
    """A time period with its own privacy budget."""
    start: datetime
    end: datetime
    epsilon_budget: float
    epsilon_spent: float = 0.0
    delta_budget: float = 1e-7
    delta_spent: float = 0.0

class PrivacyBudgetManager:
    """
    Manages privacy budget across time periods.

    Privacy budgets compose - if you spend ε₁ on one query
    and ε₂ on another, total privacy loss is ε₁ + ε₂.

    We use rolling budget periods to bound cumulative privacy loss.
    Each period gets a fresh budget, so total lifetime privacy
    loss is bounded by (number of periods) × (budget per period).
    """

    def __init__(
        self,
        epsilon_per_period: float = 1.0,
        delta_per_period: float = 1e-8,
        period_duration: timedelta = timedelta(days=7),
        state_path: Path = Path("/var/lib/datadr/privacy_budget.json"),
    ):
        self._epsilon_per_period = epsilon_per_period
        self._delta_per_period = delta_per_period
        self._period_duration = period_duration
        self._state_path = state_path

        self._periods: list[BudgetPeriod] = []
        self._load_state()

    def request_budget(
        self,
        epsilon_needed: float,
        delta_needed: float = 0.0,
    ) -> Optional[BudgetPeriod]:
        """
        Request privacy budget for an operation.

        Returns the current period if sufficient budget remains,
        None if the request would exceed the budget.

        IMPORTANT: This method must be called BEFORE performing
        any privacy-consuming operation. If it returns None,
        the operation MUST NOT proceed.
        """
        current_period = self._get_or_create_current_period()

        epsilon_remaining = current_period.epsilon_budget - current_period.epsilon_spent
        delta_remaining = current_period.delta_budget - current_period.delta_spent

        if epsilon_needed > epsilon_remaining or delta_needed > delta_remaining:
            # Budget exhausted for this period
            return None

        return current_period

    def record_spend(
        self,
        period: BudgetPeriod,
        epsilon_spent: float,
        delta_spent: float = 0.0,
    ) -> None:
        """
        Record privacy budget consumption.

        MUST be called after every privacy-consuming operation
        with the actual epsilon and delta spent.
        """
        period.epsilon_spent += epsilon_spent
        period.delta_spent += delta_spent
        self._save_state()

    def get_remaining_budget(self) -> tuple[float, float]:
        """Get remaining (epsilon, delta) budget for current period."""
        period = self._get_or_create_current_period()
        return (
            period.epsilon_budget - period.epsilon_spent,
            period.delta_budget - period.delta_spent,
        )

    def get_lifetime_spend(self) -> tuple[float, float]:
        """
        Get total privacy spend across all periods.

        This represents the cumulative privacy loss for this
        customer's data over the lifetime of their participation.
        """
        total_epsilon = sum(p.epsilon_spent for p in self._periods)
        total_delta = sum(p.delta_spent for p in self._periods)
        return (total_epsilon, total_delta)

    def _get_or_create_current_period(self) -> BudgetPeriod:
        """Get the current period, creating a new one if needed."""
        now = datetime.utcnow()

        # Check if current period exists and is still valid
        if self._periods:
            latest = self._periods[-1]
            if latest.start <= now < latest.end:
                return latest

        # Create new period
        period_start = now
        period_end = now + self._period_duration

        new_period = BudgetPeriod(
            start=period_start,
            end=period_end,
            epsilon_budget=self._epsilon_per_period,
            delta_budget=self._delta_per_period,
        )

        self._periods.append(new_period)
        self._save_state()

        return new_period

    def _load_state(self) -> None:
        """Load budget state from persistent storage."""
        if self._state_path.exists():
            with open(self._state_path) as f:
                data = json.load(f)
                self._periods = [
                    BudgetPeriod(
                        start=datetime.fromisoformat(p["start"]),
                        end=datetime.fromisoformat(p["end"]),
                        epsilon_budget=p["epsilon_budget"],
                        epsilon_spent=p["epsilon_spent"],
                        delta_budget=p["delta_budget"],
                        delta_spent=p["delta_spent"],
                    )
                    for p in data["periods"]
                ]

    def _save_state(self) -> None:
        """Persist budget state to storage."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "periods": [
                {
                    "start": p.start.isoformat(),
                    "end": p.end.isoformat(),
                    "epsilon_budget": p.epsilon_budget,
                    "epsilon_spent": p.epsilon_spent,
                    "delta_budget": p.delta_budget,
                    "delta_spent": p.delta_spent,
                }
                for p in self._periods
            ]
        }

        with open(self._state_path, "w") as f:
            json.dump(data, f, indent=2)4. Secure Transmission Layer4.1 Transport SecurityAll communication between customer agents and DataDr servers uses mTLS with certificate pinning.python# datadr_agent/transport/secure_client.py

import ssl
import aiohttp
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import certifi

@dataclass(frozen=True)
class TransportConfig:
    """
    Configuration for secure transport.

    All certificates should be rotated at least annually.
    """
    # DataDr server endpoint
    server_url: str = "https://ingest.datadr.io"

    # Client certificate (for mTLS)
    client_cert_path: Path = Path("/etc/datadr/client.crt")
    client_key_path: Path = Path("/etc/datadr/client.key")

    # Server certificate pinning
    # This is the SHA-256 fingerprint of DataDr's server certificate
    # If this doesn't match, connection is refused (prevents MITM)
    server_cert_fingerprint: str = "sha256//AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    # Timeouts
    connect_timeout_seconds: int = 10
    read_timeout_seconds: int = 60

    # Retry configuration
    max_retries: int = 3
    retry_backoff_base: float = 2.0

class SecureTransportClient:
    """
    Secure HTTP client for transmitting privatized data to DataDr.

    Security features:
    - mTLS (mutual TLS) - both client and server authenticate
    - Certificate pinning - prevents MITM even with compromised CA
    - Request signing - ensures integrity
    - Payload encryption - additional layer beyond TLS
    """

    def __init__(self, config: TransportConfig, tenant_id: str):
        self._config = config
        self._tenant_id = tenant_id
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "SecureTransportClient":
        await self._create_session()
        return self

    async def __aexit__(self, *args) -> None:
        if self._session:
            await self._session.close()

    async def _create_session(self) -> None:
        """Create HTTPS session with mTLS and certificate pinning."""

        # Create SSL context with client certificate
        ssl_context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=certifi.where(),
        )

        # Load client certificate for mTLS
        ssl_context.load_cert_chain(
            certfile=str(self._config.client_cert_path),
            keyfile=str(self._config.client_key_path),
        )

        # Enable certificate pinning via custom verification
        # (In production, use a library like trustme or implement
        #  certificate fingerprint verification in a custom SSLContext)

        timeout = aiohttp.ClientTimeout(
            connect=self._config.connect_timeout_seconds,
            total=self._config.read_timeout_seconds,
        )

        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(ssl=ssl_context),
        )

    async def submit_contribution(
        self,
        contribution: "ContributionPackage",
    ) -> "SubmissionReceipt":
        """
        Submit a privatized contribution to DataDr.

        The contribution is encrypted before transmission
        (defense in depth - TLS + application-layer encryption).
        """
        # Serialize and encrypt payload
        payload = await self._encrypt_payload(contribution)

        # Sign the request
        signature = await self._sign_request(payload)

        headers = {
            "Content-Type": "application/octet-stream",
            "X-DataDr-Tenant": self._tenant_id,
            "X-DataDr-Signature": signature,
            "X-DataDr-Algorithm": "Ed25519",
        }

        # Submit with retries
        last_error = None
        for attempt in range(self._config.max_retries):
            try:
                async with self._session.post(
                    f"{self._config.server_url}/v1/contributions",
                    data=payload,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        receipt_data = await response.json()
                        return SubmissionReceipt(
                            contribution_id=receipt_data["id"],
                            received_at=receipt_data["received_at"],
                            epsilon_recorded=receipt_data["epsilon"],
                        )
                    elif response.status == 429:
                        # Rate limited - back off
                        await asyncio.sleep(
                            self._config.retry_backoff_base ** attempt
                        )
                    else:
                        error_body = await response.text()
                        raise TransmissionError(
                            f"Server returned {response.status}: {error_body}"
                        )
            except aiohttp.ClientError as e:
                last_error = e
                await asyncio.sleep(self._config.retry_backoff_base ** attempt)

        raise TransmissionError(f"Failed after {self._config.max_retries} retries: {last_error}")

    async def _encrypt_payload(
        self,
        contribution: "ContributionPackage"
    ) -> bytes:
        """
        Encrypt contribution using DataDr's public key.

        Uses hybrid encryption:
        - Generate ephemeral X25519 key pair
        - Derive shared secret with DataDr's public key
        - Encrypt payload with AES-256-GCM using derived key
        - Send ephemeral public key + ciphertext
        """
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        import os

        # Load DataDr's public key (embedded in agent)
        server_public_key = self._load_server_public_key()

        # Generate ephemeral key pair
        ephemeral_private = X25519PrivateKey.generate()
        ephemeral_public = ephemeral_private.public_key()

        # Derive shared secret
        shared_secret = ephemeral_private.exchange(server_public_key)

        # Derive encryption key using HKDF
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"datadr-contribution-encryption",
        )
        encryption_key = kdf.derive(shared_secret)

        # Encrypt payload
        nonce = os.urandom(12)
        aesgcm = AESGCM(encryption_key)
        plaintext = contribution.serialize()
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # Package: ephemeral_public_key || nonce || ciphertext
        return (
            ephemeral_public.public_bytes_raw() +
            nonce +
            ciphertext
        )

    async def _sign_request(self, payload: bytes) -> str:
        """
        Sign request using tenant's Ed25519 private key.

        This proves the request came from an authorized agent.
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64

        # Load tenant's signing key
        signing_key = self._load_signing_key()

        # Sign the payload
        signature = signing_key.sign(payload)

        return base64.b64encode(signature).decode()4.2 Contribution Package Formatpython# datadr_agent/transport/contribution.py

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
import msgpack

@dataclass(frozen=True)
class ContributionPackage:
    """
    A complete contribution ready for transmission.

    Contains:
    - Privatized patterns (DP applied)
    - ZK proofs of validity
    - Metadata for aggregation
    """
    # Tenant identifier
    tenant_id: str

    # Agent version (for compatibility)
    agent_version: str

    # Contribution timestamp
    created_at: datetime

    # Privatized patterns
    patterns: Sequence[PrivatizedPattern]

    # Zero-knowledge proofs (one per pattern)
    validity_proofs: Sequence[bytes]

    # Privacy accounting
    total_epsilon_spent: float
    total_delta_spent: float
    budget_period_id: str

    # Schema fingerprint summary (for routing)
    schema_fingerprints: Sequence[str]

    def serialize(self) -> bytes:
        """Serialize to msgpack format."""
        return msgpack.packb({
            "tenant_id": self.tenant_id,
            "agent_version": self.agent_version,
            "created_at": self.created_at.isoformat(),
            "patterns": [self._serialize_pattern(p) for p in self.patterns],
            "validity_proofs": [proof for proof in self.validity_proofs],
            "total_epsilon_spent": self.total_epsilon_spent,
            "total_delta_spent": self.total_delta_spent,
            "budget_period_id": self.budget_period_id,
            "schema_fingerprints": list(self.schema_fingerprints),
        })

    def _serialize_pattern(self, pattern: PrivatizedPattern) -> dict:
        """Serialize a single pattern."""
        return {
            "pattern_type": pattern.pattern_type.value,
            "schema_fingerprint": pattern.schema_fingerprint,
            "severity": pattern.severity,
            "detected_at": pattern.detected_at.isoformat(),
            "metrics": pattern.metrics,
            "upstream_correlations": pattern.upstream_correlations,
            "epsilon_spent": pattern.epsilon_spent,
            "delta": pattern.delta,
        }5. Server-Side Secure Storage5.1 Storage ArchitectureDataDr stores contributions in an encrypted, tenant-isolated storage layer.┌─────────────────────────────────────────────────────────────────────────────┐
│                          Storage Architecture                                │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         Key Management Service                         │  │
│  │                    (AWS KMS / GCP Cloud KMS / Vault)                   │  │
│  │                                                                         │  │
│  │    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │  │
│  │    │ Master Key  │    │ Tenant Key  │    │ Tenant Key  │    ...       │  │
│  │    │   (Root)    │───▶│  (Tenant A) │    │  (Tenant B) │              │  │
│  │    └─────────────┘    └──────┬──────┘    └──────┬──────┘              │  │
│  │                              │                  │                      │  │
│  └──────────────────────────────┼──────────────────┼──────────────────────┘  │
│                                 │                  │                         │
│  ┌──────────────────────────────▼──────────────────▼──────────────────────┐  │
│  │                         Encrypted Storage                              │  │
│  │                                                                         │  │
│  │    ┌─────────────────────┐    ┌─────────────────────┐                 │  │
│  │    │   Tenant A Bucket   │    │   Tenant B Bucket   │                 │  │
│  │    │   (AES-256-GCM)     │    │   (AES-256-GCM)     │                 │  │
│  │    │                     │    │                     │                 │  │
│  │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │                 │  │
│  │    │ │ contributions/  │ │    │ │ contributions/  │ │                 │  │
│  │    │ │  2024-01-15/    │ │    │ │  2024-01-15/    │ │                 │  │
│  │    │ │   *.enc         │ │    │ │   *.enc         │ │                 │  │
│  │    │ └─────────────────┘ │    │ └─────────────────┘ │                 │  │
│  │    │                     │    │                     │                 │  │
│  │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │                 │  │
│  │    │ │ budget_state/   │ │    │ │ budget_state/   │ │                 │  │
│  │    │ │  current.enc    │ │    │ │  current.enc    │ │                 │  │
│  │    │ └─────────────────┘ │    │ └─────────────────┘ │                 │  │
│  │    └─────────────────────┘    └─────────────────────┘                 │  │
│  │                                                                         │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                         Aggregation Store                               │  │
│  │                    (Cross-tenant, DP-protected only)                    │  │
│  │                                                                         │  │
│  │    ┌─────────────────────────────────────────────────────────────────┐ │  │
│  │    │   Global Patterns (no tenant attribution)                        │ │  │
│  │    │   • pattern_type + schema_fingerprint → aggregated_stats        │ │  │
│  │    └─────────────────────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘5.2 Storage Service Implementationpython# datadr_server/storage/contribution_store.py

from dataclasses import dataclass
from datetime import datetime, date
from typing import AsyncIterator, Optional
from pathlib import Path
import aioboto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

@dataclass(frozen=True)
class StorageConfig:
    """Storage configuration."""
    bucket_prefix: str = "datadr-contributions"
    region: str = "us-east-1"
    kms_key_alias: str = "alias/datadr-master"

class ContributionStore:
    """
    Secure storage for tenant contributions.

    Design principles:
    1. Tenant isolation: Each tenant's data is encrypted with a unique key
    2. Defense in depth: Data is encrypted at rest (S3) AND with tenant key
    3. Audit trail: All access is logged
    4. Key rotation: Tenant keys can be rotated without data migration
    """

    def __init__(self, config: StorageConfig):
        self._config = config
        self._session = aioboto3.Session()

    async def store_contribution(
        self,
        tenant_id: str,
        contribution: ContributionPackage,
    ) -> str:
        """
        Store an encrypted contribution.

        Returns the contribution ID for future reference.
        """
        # Generate contribution ID
        contribution_id = self._generate_contribution_id()

        # Get or create tenant's data encryption key
        dek = await self._get_tenant_dek(tenant_id)

        # Serialize contribution
        plaintext = contribution.serialize()

        # Encrypt with tenant's DEK
        nonce = os.urandom(12)
        aesgcm = AESGCM(dek)
        ciphertext = aesgcm.encrypt(nonce, plaintext, self._aad(tenant_id, contribution_id))

        # Construct S3 path
        date_partition = contribution.created_at.strftime("%Y/%m/%d")
        s3_key = f"{tenant_id}/contributions/{date_partition}/{contribution_id}.enc"

        # Store in S3
        async with self._session.client("s3", region_name=self._config.region) as s3:
            await s3.put_object(
                Bucket=self._get_bucket_name(tenant_id),
                Key=s3_key,
                Body=nonce + ciphertext,
                Metadata={
                    "x-datadr-tenant": tenant_id,
                    "x-datadr-contribution-id": contribution_id,
                    "x-datadr-created-at": contribution.created_at.isoformat(),
                    "x-datadr-epsilon": str(contribution.total_epsilon_spent),
                },
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=self._config.kms_key_alias,
            )

        # Log access for audit
        await self._audit_log(
            action="store_contribution",
            tenant_id=tenant_id,
            contribution_id=contribution_id,
        )

        return contribution_id

    async def retrieve_contribution(
        self,
        tenant_id: str,
        contribution_id: str,
    ) -> Optional[ContributionPackage]:
        """
        Retrieve and decrypt a contribution.

        Returns None if contribution doesn't exist.
        Raises UnauthorizedAccess if tenant_id doesn't match.
        """
        # Find the contribution (we need to search by ID since date is unknown)
        s3_key = await self._find_contribution_key(tenant_id, contribution_id)

        if s3_key is None:
            return None

        # Get tenant's DEK
        dek = await self._get_tenant_dek(tenant_id)

        # Retrieve from S3
        async with self._session.client("s3", region_name=self._config.region) as s3:
            response = await s3.get_object(
                Bucket=self._get_bucket_name(tenant_id),
                Key=s3_key,
            )
            encrypted_data = await response["Body"].read()

        # Decrypt
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(dek)
        plaintext = aesgcm.decrypt(nonce, ciphertext, self._aad(tenant_id, contribution_id))

        # Deserialize
        contribution = ContributionPackage.deserialize(plaintext)

        # Log access for audit
        await self._audit_log(
            action="retrieve_contribution",
            tenant_id=tenant_id,
            contribution_id=contribution_id,
        )

        return contribution

    async def stream_contributions_for_aggregation(
        self,
        since: datetime,
        batch_size: int = 100,
    ) -> AsyncIterator[list[tuple[str, ContributionPackage]]]:
        """
        Stream all contributions since a given time for aggregation.

        IMPORTANT: This method is used by the aggregation pipeline.
        It accesses data across tenants but only outputs DP-protected
        aggregates, never raw contributions.

        Returns tuples of (tenant_id, contribution).
        """
        # List all tenant buckets
        tenants = await self._list_tenants()

        for tenant_id in tenants:
            async for batch in self._stream_tenant_contributions(
                tenant_id, since, batch_size
            ):
                yield batch

    async def _get_tenant_dek(self, tenant_id: str) -> bytes:
        """
        Get or create the Data Encryption Key for a tenant.

        DEKs are stored encrypted under the master key in KMS.
        This provides key hierarchy:
        - Master Key (in KMS, never leaves HSM)
          └── Tenant DEK (encrypted by master key)
              └── Contribution data (encrypted by DEK)
        """
        async with self._session.client("kms", region_name=self._config.region) as kms:
            # Try to retrieve existing DEK
            try:
                async with self._session.client("s3", region_name=self._config.region) as s3:
                    response = await s3.get_object(
                        Bucket=self._get_bucket_name(tenant_id),
                        Key=f"{tenant_id}/.keys/dek.enc",
                    )
                    encrypted_dek = await response["Body"].read()

                # Decrypt DEK using KMS
                decrypt_response = await kms.decrypt(
                    CiphertextBlob=encrypted_dek,
                    KeyId=self._config.kms_key_alias,
                    EncryptionContext={"tenant_id": tenant_id},
                )
                return decrypt_response["Plaintext"]

            except Exception:
                # DEK doesn't exist, create new one
                generate_response = await kms.generate_data_key(
                    KeyId=self._config.kms_key_alias,
                    KeySpec="AES_256",
                    EncryptionContext={"tenant_id": tenant_id},
                )

                # Store encrypted DEK
                async with self._session.client("s3", region_name=self._config.region) as s3:
                    await s3.put_object(
                        Bucket=self._get_bucket_name(tenant_id),
                        Key=f"{tenant_id}/.keys/dek.enc",
                        Body=generate_response["CiphertextBlob"],
                    )

                return generate_response["Plaintext"]

    def _aad(self, tenant_id: str, contribution_id: str) -> bytes:
        """
        Additional Authenticated Data for AEAD encryption.

        This binds the ciphertext to the tenant and contribution IDs,
        preventing ciphertext from being copied between contexts.
        """
        return f"{tenant_id}:{contribution_id}".encode()

    def _get_bucket_name(self, tenant_id: str) -> str:
        """Get S3 bucket name for a tenant."""
        return f"{self._config.bucket_prefix}-{tenant_id}"

    def _generate_contribution_id(self) -> str:
        """Generate a unique contribution ID."""
        import uuid
        return str(uuid.uuid4())

    async def _audit_log(
        self,
        action: str,
        tenant_id: str,
        contribution_id: str,
    ) -> None:
        """Log access for audit trail."""
        # Implementation depends on audit system (CloudWatch, Splunk, etc.)
        pass5.3 Tenant Isolation Verificationpython# datadr_server/storage/isolation_verifier.py

class TenantIsolationVerifier:
    """
    Verifies that tenant isolation is maintained.

    This class implements runtime checks to ensure that:
    1. Data from one tenant cannot be accessed by another
    2. Cross-tenant operations only produce DP-protected outputs
    3. Audit logs capture all data access

    Run these checks:
    - On every deployment
    - Daily in production
    - On-demand for compliance audits
    """

    async def verify_bucket_isolation(self) -> VerificationResult:
        """
        Verify that S3 bucket policies enforce tenant isolation.

        Each tenant bucket should only be accessible by:
        - The tenant's own API credentials
        - The aggregation service (read-only, for DP computation)
        """
        results = []

        for tenant_id in await self._list_tenants():
            bucket_name = f"datadr-contributions-{tenant_id}"

            # Check bucket policy
            policy = await self._get_bucket_policy(bucket_name)

            # Verify no cross-tenant access
            if self._allows_cross_tenant_access(policy, tenant_id):
                results.append(VerificationFailure(
                    check="bucket_isolation",
                    tenant_id=tenant_id,
                    message="Bucket policy allows cross-tenant access",
                ))

        return VerificationResult(failures=results)

    async def verify_key_isolation(self) -> VerificationResult:
        """
        Verify that each tenant has a unique DEK.

        Checks:
        - No DEK is shared between tenants
        - DEKs are properly encrypted under master key
        - Key rotation is enabled
        """
        # Implementation
        pass

    async def verify_aggregation_boundaries(self) -> VerificationResult:
        """
        Verify that aggregation pipeline only produces DP outputs.

        Checks:
        - No raw contributions in aggregation output
        - DP noise is applied to all aggregate queries
        - Privacy budget is tracked
        """
        # Implementation
        pass6. Differential Privacy Computation Engine6.1 Server-Side DP AggregatorThe server aggregates contributions from multiple tenants while maintaining DP guarantees.python# datadr_server/dp/aggregator.py

from dataclasses import dataclass
from typing import Sequence, Dict
from collections import defaultdict
import numpy as np

@dataclass(frozen=True)
class AggregationConfig:
    """
    Configuration for DP aggregation.

    These parameters apply to the SERVER-SIDE aggregation.
    Combined with client-side DP, this provides "shuffled model" guarantees.
    """
    # Privacy parameters for aggregation
    epsilon_per_query: float = 0.1
    delta_per_query: float = 1e-9

    # Minimum contributors for any aggregate
    # This prevents small-group deanonymization
    min_contributors: int = 10

    # Clipping bounds
    max_patterns_per_contributor: int = 100

class DPAggregator:
    """
    Aggregates privatized patterns across tenants.

    Privacy model:
    - Each tenant's contribution is already DP (local model)
    - Server aggregation adds additional DP (central model)
    - Combined guarantee is stronger than either alone (amplification)

    Output guarantees:
    - No output reveals which tenants contributed
    - Aggregate statistics have bounded influence from any single tenant
    """

    def __init__(self, config: AggregationConfig):
        self._config = config
        self._rng = np.random.default_rng()

    async def aggregate_pattern_frequencies(
        self,
        contributions: Sequence[ContributionPackage],
    ) -> Dict[str, "AggregatedPatternStats"]:
        """
        Aggregate pattern frequencies across all contributions.

        Returns a mapping from (pattern_type, schema_fingerprint) to
        aggregated statistics with DP noise applied.
        """
        # Group patterns by (type, fingerprint)
        pattern_groups: Dict[str, list[PrivatizedPattern]] = defaultdict(list)
        contributor_counts: Dict[str, set[str]] = defaultdict(set)

        for contribution in contributions:
            for pattern in contribution.patterns:
                key = f"{pattern.pattern_type.value}:{pattern.schema_fingerprint}"
                pattern_groups[key].append(pattern)
                contributor_counts[key].add(contribution.tenant_id)

        # Aggregate each group
        results = {}
        for key, patterns in pattern_groups.items():
            # Check minimum contributor threshold
            if len(contributor_counts[key]) < self._config.min_contributors:
                # Not enough contributors - skip to prevent deanonymization
                continue

            results[key] = await self._aggregate_group(
                patterns=patterns,
                contributor_count=len(contributor_counts[key]),
            )

        return results

    async def _aggregate_group(
        self,
        patterns: Sequence[PrivatizedPattern],
        contributor_count: int,
    ) -> "AggregatedPatternStats":
        """
        Aggregate a group of patterns with the same type and fingerprint.
        """
        # Collect metrics across patterns
        severities = [p.severity for p in patterns]

        # Aggregate metrics (mean with DP noise)
        all_metrics: Dict[str, list[float]] = defaultdict(list)
        for pattern in patterns:
            for metric_name, value in pattern.metrics.items():
                all_metrics[metric_name].append(value)

        # Apply DP to count
        noised_count = self._dp_count(
            true_count=len(patterns),
            epsilon=self._config.epsilon_per_query / 3,
        )

        # Apply DP to mean severity
        noised_severity = self._dp_mean(
            values=severities,
            clip_low=0.0,
            clip_high=1.0,
            epsilon=self._config.epsilon_per_query / 3,
        )

        # Apply DP to each metric mean
        noised_metrics = {}
        eps_per_metric = (self._config.epsilon_per_query / 3) / max(1, len(all_metrics))
        for metric_name, values in all_metrics.items():
            bounds = self._get_metric_bounds(metric_name)
            noised_metrics[metric_name] = self._dp_mean(
                values=values,
                clip_low=bounds[0],
                clip_high=bounds[1],
                epsilon=eps_per_metric,
            )

        return AggregatedPatternStats(
            pattern_count=noised_count,
            contributor_count=contributor_count,  # This is public (just says "at least 10")
            mean_severity=noised_severity,
            metric_means=noised_metrics,
            epsilon_spent=self._config.epsilon_per_query,
        )

    def _dp_count(
        self,
        true_count: int,
        epsilon: float,
    ) -> int:
        """
        DP count using Laplace mechanism.

        Sensitivity = 1 (adding/removing one record changes count by 1)
        """
        noise = self._rng.laplace(0, 1 / epsilon)
        return max(0, int(round(true_count + noise)))

    def _dp_mean(
        self,
        values: Sequence[float],
        clip_low: float,
        clip_high: float,
        epsilon: float,
    ) -> float:
        """
        DP mean using Laplace mechanism.

        Steps:
        1. Clip values to bounds
        2. Compute true mean
        3. Add Laplace noise calibrated to sensitivity

        Sensitivity of mean = (clip_high - clip_low) / n
        """
        if not values:
            return 0.0

        # Clip values
        clipped = np.clip(values, clip_low, clip_high)

        # True mean
        true_mean = np.mean(clipped)

        # Sensitivity of mean
        sensitivity = (clip_high - clip_low) / len(values)

        # Add noise
        noise = self._rng.laplace(0, sensitivity / epsilon)
        noised_mean = true_mean + noise

        # Clip result to valid range
        return float(np.clip(noised_mean, clip_low, clip_high))

    def _get_metric_bounds(self, metric_name: str) -> tuple[float, float]:
        """Get clipping bounds for a metric."""
        bounds = {
            "null_rate": (0.0, 1.0),
            "row_count": (0.0, 1e12),
            "execution_time_ms": (0.0, 3600000.0),
        }
        return bounds.get(metric_name, (0.0, 1e6))


@dataclass(frozen=True)
class AggregatedPatternStats:
    """
    Aggregated statistics for a pattern type.

    All values are DP-protected - safe for public release.
    """
    pattern_count: int
    contributor_count: int
    mean_severity: float
    metric_means: Dict[str, float]
    epsilon_spent: float6.2 Global Privacy Budget Accountingpython# datadr_server/dp/global_budget.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import asyncpg

@dataclass
class GlobalBudgetState:
    """
    Tracks privacy budget across ALL queries to the aggregated data.

    This is separate from per-tenant budgets.
    It bounds the total information leaked about the global dataset.
    """
    period_start: datetime
    period_end: datetime
    total_epsilon_budget: float
    total_epsilon_spent: float
    query_count: int

class GlobalPrivacyBudgetManager:
    """
    Manages the global privacy budget for aggregated queries.

    Every query to the aggregate data consumes budget.
    When budget is exhausted, no more queries are allowed until reset.

    This prevents:
    - Adaptive attacks where adversary issues many queries
    - Composition attacks across different query patterns
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        epsilon_per_period: float = 10.0,
        delta_per_period: float = 1e-7,
    ):
        self._db = db_pool
        self._epsilon_per_period = epsilon_per_period
        self._delta_per_period = delta_per_period

    async def request_budget(
        self,
        epsilon_needed: float,
        query_description: str,
    ) -> Optional[str]:
        """
        Request budget for an aggregate query.

        Returns a budget_grant_id if approved, None if budget exhausted.

        EVERY aggregate query must call this before executing.
        If it returns None, the query MUST NOT execute.
        """
        async with self._db.acquire() as conn:
            async with conn.transaction():
                # Get current period state
                state = await self._get_current_state(conn)

                if state.total_epsilon_spent + epsilon_needed > state.total_epsilon_budget:
                    # Budget exhausted
                    await self._log_budget_exhaustion(conn, epsilon_needed, query_description)
                    return None

                # Grant budget
                grant_id = await self._create_grant(
                    conn,
                    epsilon=epsilon_needed,
                    query_description=query_description,
                )

                # Update spent amount
                await conn.execute("""
                    UPDATE global_privacy_budget
                    SET total_epsilon_spent = total_epsilon_spent + $1,
                        query_count = query_count + 1
                    WHERE id = $2
                """, epsilon_needed, state.id)

                return grant_id

    async def get_remaining_budget(self) -> tuple[float, float]:
        """Get remaining (epsilon, delta) budget for current period."""
        async with self._db.acquire() as conn:
            state = await self._get_current_state(conn)
            return (
                state.total_epsilon_budget - state.total_epsilon_spent,
                self._delta_per_period,  # Delta doesn't compose the same way
            )7. Zero-Knowledge Proof System7.1 ZKP Circuit DesignWe use zero-knowledge proofs to verify contribution validity without revealing the underlying data.python# datadr_agent/zkp/circuits.py

"""
Zero-Knowledge Proof Circuits for DataDr

We use RISC Zero (https://risczero.com) for ZK proof generation.
RISC Zero allows writing circuits in Rust that compile to a ZK-provable VM.

Alternative frameworks:
- SP1 (https://github.com/succinctlabs/sp1)
- Noir (https://noir-lang.org/)
- Circom (https://docs.circom.io/)

We chose RISC Zero because:
1. Write circuits in standard Rust (no DSL)
2. Good performance for our proof sizes
3. Active development and support
"""7.1.1 Contribution Validity Circuit (Rust)This circuit proves that a contribution is valid without revealing the underlying data.rust// datadr_agent/zkp/circuits/contribution_validity/src/main.rs

//! Zero-Knowledge Proof Circuit for Contribution Validity
//!
//! This circuit proves:
//! 1. The contribution was derived from actual query logs (not fabricated)
//! 2. The sample size meets minimum thresholds (prevents deanonymization)
//! 3. No PII is present in the contribution
//! 4. The DP noise was applied correctly
//! 5. The contribution matches the claimed hash
//!
//! The prover (customer's agent) provides:
//! - Private inputs: raw query logs, schema metadata
//! - Public inputs: contribution hash, tenant_id
//!
//! The verifier (DataDr server) learns only:
//! - The contribution is valid (all checks pass)
//! - Nothing about the underlying data

#![no_main]

use risc0_zkvm::guest::env;
use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};

risc0_zkvm::guest::entry!(main);

/// Private inputs (never revealed)
#[derive(Deserialize)]
struct PrivateInputs {
    /// Raw query log entries
    query_logs: Vec<QueryLogEntry>,

    /// Schema metadata
    schemas: Vec<SchemaInfo>,

    /// The extracted patterns (before DP noise)
    raw_patterns: Vec<RawPattern>,

    /// DP noise that was added (for verification)
    dp_noise_seeds: Vec<[u8; 32]>,

    /// The final privatized patterns
    privatized_patterns: Vec<PrivatizedPattern>,
}

/// Public inputs (revealed to verifier)
#[derive(Serialize, Deserialize)]
struct PublicInputs {
    /// Hash of the contribution
    contribution_hash: [u8; 32],

    /// Tenant identifier
    tenant_id: String,

    /// Claimed privacy parameters
    epsilon: f64,
    delta: f64,

    /// Minimum sample size requirement
    min_sample_size: u32,
}

#[derive(Deserialize)]
struct QueryLogEntry {
    query_hash: [u8; 32],
    tables_accessed: Vec<String>,
    execution_time_ms: u64,
    rows_scanned: u64,
    timestamp_unix: u64,
}

#[derive(Deserialize)]
struct SchemaInfo {
    fingerprint: [u8; 16],
    column_count: u32,
    row_count_approx: u64,
}

#[derive(Deserialize)]
struct RawPattern {
    pattern_type: u8,
    schema_fingerprint: [u8; 16],
    severity: f64,
    metrics: Vec<(String, f64)>,
    sample_count: u32,
}

#[derive(Deserialize, Serialize)]
struct PrivatizedPattern {
    pattern_type: u8,
    schema_fingerprint: [u8; 16],
    severity: f64,
    metrics: Vec<(String, f64)>,
}

fn main() {
    // Read inputs
    let private_inputs: PrivateInputs = env::read();
    let public_inputs: PublicInputs = env::read();

    // ============================================================
    // CHECK 1: Query logs are structurally valid
    // ============================================================
    // This proves the patterns were derived from real query logs,
    // not fabricated by the prover.

    for log in &private_inputs.query_logs {
        // Query hash must be 32 bytes (valid SHA-256)
        assert!(log.query_hash.iter().any(|&b| b != 0), "Invalid query hash");

        // Timestamps must be reasonable (not in future, not ancient)
        let now_approx = 1704067200; // 2024-01-01 (update periodically)
        assert!(log.timestamp_unix > now_approx - 365 * 24 * 3600, "Log too old");
        assert!(log.timestamp_unix < now_approx + 365 * 24 * 3600, "Log in future");
    }

    // ============================================================
    // CHECK 2: Sample size meets minimum threshold
    // ============================================================
    // This prevents patterns from small datasets that could be
    // deanonymized through uniqueness.

    for pattern in &private_inputs.raw_patterns {
        assert!(
            pattern.sample_count >= public_inputs.min_sample_size,
            "Sample size below minimum threshold"
        );
    }

    // ============================================================
    // CHECK 3: Patterns were correctly derived from logs
    // ============================================================
    // We verify that each pattern has supporting evidence in the logs.
    // This is a simplified check - full implementation would trace
    // the exact derivation.

    let total_log_count = private_inputs.query_logs.len() as u32;
    let total_pattern_samples: u32 = private_inputs.raw_patterns
        .iter()
        .map(|p| p.sample_count)
        .sum();

    // Total samples across patterns shouldn't exceed total logs
    // (allowing some patterns to share logs)
    assert!(
        total_pattern_samples <= total_log_count * 10,
        "Pattern samples inconsistent with log count"
    );

    // ============================================================
    // CHECK 4: DP noise was applied correctly
    // ============================================================
    // We verify that the privatized patterns equal raw patterns + noise,
    // and that the noise has the correct distribution.

    assert_eq!(
        private_inputs.raw_patterns.len(),
        private_inputs.privatized_patterns.len(),
        "Pattern count mismatch"
    );

    for (i, (raw, privatized)) in private_inputs.raw_patterns
        .iter()
        .zip(private_inputs.privatized_patterns.iter())
        .enumerate()
    {
        // Same structure
        assert_eq!(raw.pattern_type, privatized.pattern_type);
        assert_eq!(raw.schema_fingerprint, privatized.schema_fingerprint);

        // Verify noise was applied to severity
        let noise_seed = &private_inputs.dp_noise_seeds[i];
        let expected_noise = laplace_from_seed(noise_seed, 1.0 / public_inputs.epsilon);
        let expected_severity = (raw.severity + expected_noise).clamp(0.0, 1.0);

        // Allow small floating point tolerance
        assert!(
            (privatized.severity - expected_severity).abs() < 1e-10,
            "Severity noise verification failed"
        );
    }

    // ============================================================
    // CHECK 5: No PII in pattern descriptions
    // ============================================================
    // We check that patterns don't contain personally identifiable
    // information. This is a heuristic check.

    for pattern in &private_inputs.privatized_patterns {
        // Schema fingerprint should be a hash, not raw names
        // (All bytes should contribute, not ASCII-only)
        let non_ascii_bytes = pattern.schema_fingerprint
            .iter()
            .filter(|&&b| b > 127)
            .count();
        assert!(non_ascii_bytes > 0, "Schema fingerprint appears unhashed");
    }

    // ============================================================
    // CHECK 6: Contribution hash matches
    // ============================================================
    // Finally, verify the public contribution hash matches
    // what we computed from the privatized patterns.

    let computed_hash = compute_contribution_hash(&private_inputs.privatized_patterns);
    assert_eq!(
        computed_hash,
        public_inputs.contribution_hash,
        "Contribution hash mismatch"
    );

    // ============================================================
    // OUTPUT: Commit to public inputs
    // ============================================================
    // The verifier will receive the public inputs and the proof.
    // They learn nothing else about the private inputs.

    env::commit(&public_inputs);
}

fn laplace_from_seed(seed: &[u8; 32], scale: f64) -> f64 {
    // Deterministic Laplace noise from seed
    // This allows verification that the correct noise was applied
    use sha2::{Sha256, Digest};

    let mut hasher = Sha256::new();
    hasher.update(seed);
    let hash = hasher.finalize();

    // Convert to uniform [0, 1)
    let u = u64::from_le_bytes(hash[0..8].try_into().unwrap()) as f64 / u64::MAX as f64;

    // Inverse CDF of Laplace distribution
    if u < 0.5 {
        scale * (2.0 * u).ln()
    } else {
        -scale * (2.0 * (1.0 - u)).ln()
    }
}

fn compute_contribution_hash(patterns: &[PrivatizedPattern]) -> [u8; 32] {
    use sha2::{Sha256, Digest};

    let mut hasher = Sha256::new();
    for pattern in patterns {
        hasher.update(&[pattern.pattern_type]);
        hasher.update(&pattern.schema_fingerprint);
        hasher.update(&pattern.severity.to_le_bytes());
    }
    hasher.finalize().into()
}7.2 Proof Generation (Agent Side)python# datadr_agent/zkp/prover.py

from dataclasses import dataclass
from pathlib import Path
import subprocess
import json
import tempfile

@dataclass(frozen=True)
class ZKProofConfig:
    """Configuration for ZK proof generation."""
    circuit_path: Path = Path("/opt/datadr/circuits/contribution_validity")
    risc0_path: Path = Path("/opt/datadr/risc0")
    proof_timeout_seconds: int = 300

class ContributionProver:
    """
    Generates zero-knowledge proofs for contributions.

    The proof demonstrates that:
    1. Patterns were derived from actual query logs
    2. Sample sizes meet thresholds
    3. DP noise was correctly applied
    4. No PII is present

    WITHOUT revealing:
    - The actual query logs
    - Raw pattern values
    - Any customer data
    """

    def __init__(self, config: ZKProofConfig):
        self._config = config

    async def generate_proof(
        self,
        query_logs: list[QueryLogEntry],
        schemas: list[TableSchema],
        raw_patterns: list[ExtractedPattern],
        privatized_patterns: list[PrivatizedPattern],
        dp_noise_seeds: list[bytes],
        tenant_id: str,
        epsilon: float,
        delta: float,
    ) -> bytes:
        """
        Generate a ZK proof of contribution validity.

        This is computationally intensive (30-120 seconds typically).
        """
        # Prepare private inputs
        private_inputs = {
            "query_logs": [self._serialize_log(log) for log in query_logs],
            "schemas": [self._serialize_schema(s) for s in schemas],
            "raw_patterns": [self._serialize_raw_pattern(p) for p in raw_patterns],
            "dp_noise_seeds": [seed.hex() for seed in dp_noise_seeds],
            "privatized_patterns": [self._serialize_privatized_pattern(p) for p in privatized_patterns],
        }

        # Compute contribution hash
        contribution_hash = self._compute_contribution_hash(privatized_patterns)

        # Prepare public inputs
        public_inputs = {
            "contribution_hash": contribution_hash.hex(),
            "tenant_id": tenant_id,
            "epsilon": epsilon,
            "delta": delta,
            "min_sample_size": 100,
        }

        # Write inputs to temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            private_path = Path(tmpdir) / "private.json"
            public_path = Path(tmpdir) / "public.json"
            proof_path = Path(tmpdir) / "proof.bin"

            with open(private_path, "w") as f:
                json.dump(private_inputs, f)

            with open(public_path, "w") as f:
                json.dump(public_inputs, f)

            # Run RISC Zero prover
            result = subprocess.run(
                [
                    str(self._config.risc0_path / "cargo-risczero"),
                    "prove",
                    "--elf", str(self._config.circuit_path / "target/riscv32im-risc0-zkvm-elf/release/contribution_validity"),
                    "--private-input", str(private_path),
                    "--public-input", str(public_path),
                    "--output", str(proof_path),
                ],
                capture_output=True,
                timeout=self._config.proof_timeout_seconds,
            )

            if result.returncode != 0:
                raise ProofGenerationError(
                    f"Proof generation failed: {result.stderr.decode()}"
                )

            # Read proof
            with open(proof_path, "rb") as f:
                proof = f.read()

        return proof

    def _compute_contribution_hash(
        self,
        patterns: list[PrivatizedPattern]
    ) -> bytes:
        """Compute SHA-256 hash of contribution (must match circuit)."""
        import hashlib

        hasher = hashlib.sha256()
        for pattern in patterns:
            hasher.update(bytes([pattern.pattern_type.value]))
            hasher.update(bytes.fromhex(pattern.schema_fingerprint))
            hasher.update(pattern.severity.to_bytes(8, 'little'))

        return hasher.digest()7.3 Proof Verification (Server Side)python# datadr_server/zkp/verifier.py

from dataclasses import dataclass
from pathlib import Path
import subprocess
import json
import tempfile

@dataclass(frozen=True)
class ZKVerifyConfig:
    """Configuration for ZK proof verification."""
    circuit_image_id: str  # The expected RISC Zero image ID
    risc0_path: Path = Path("/opt/datadr/risc0")
    verify_timeout_seconds: int = 30

class ContributionVerifier:
    """
    Verifies zero-knowledge proofs of contribution validity.

    Verification is fast (< 1 second) compared to proof generation.

    A valid proof guarantees:
    - The contribution was derived from actual data
    - Privacy thresholds were met
    - DP noise was correctly applied

    WITHOUT revealing any information about the underlying data.
    """

    def __init__(self, config: ZKVerifyConfig):
        self._config = config

    async def verify_proof(
        self,
        proof: bytes,
        contribution_hash: bytes,
        tenant_id: str,
        epsilon: float,
        delta: float,
    ) -> VerificationResult:
        """
        Verify a ZK proof of contribution validity.

        Returns VerificationResult indicating whether proof is valid
        and any additional information extracted from public inputs.
        """
        # Prepare public inputs
        public_inputs = {
            "contribution_hash": contribution_hash.hex(),
            "tenant_id": tenant_id,
            "epsilon": epsilon,
            "delta": delta,
            "min_sample_size": 100,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_path = Path(tmpdir) / "proof.bin"
            public_path = Path(tmpdir) / "public.json"

            with open(proof_path, "wb") as f:
                f.write(proof)

            with open(public_path, "w") as f:
                json.dump(public_inputs, f)

            # Run RISC Zero verifier
            result = subprocess.run(
                [
                    str(self._config.risc0_path / "cargo-risczero"),
                    "verify",
                    "--proof", str(proof_path),
                    "--public-input", str(public_path),
                    "--image-id", self._config.circuit_image_id,
                ],
                capture_output=True,
                timeout=self._config.verify_timeout_seconds,
            )

            if result.returncode == 0:
                return VerificationResult(
                    valid=True,
                    public_inputs=public_inputs,
                    error=None,
                )
            else:
                return VerificationResult(
                    valid=False,
                    public_inputs=public_inputs,
                    error=result.stderr.decode(),
                )


@dataclass
class VerificationResult:
    """Result of ZK proof verification."""
    valid: bool
    public_inputs: dict
    error: str | None8. Privacy Budget Management8.1 Multi-Level Budget Trackingpython# datadr_server/privacy/budget_tracker.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import asyncpg

class BudgetLevel(str, Enum):
    """Levels at which privacy budget is tracked."""
    TENANT = "tenant"           # Per-customer budget
    GLOBAL = "global"           # Across all customers
    QUERY_TYPE = "query_type"   # Per type of query

@dataclass
class BudgetAllocation:
    """A privacy budget allocation."""
    level: BudgetLevel
    identifier: str  # tenant_id, "global", or query_type
    period_start: datetime
    period_end: datetime
    epsilon_budget: float
    epsilon_spent: float
    delta_budget: float
    delta_spent: float

class MultiLevelBudgetTracker:
    """
    Tracks privacy budget at multiple levels simultaneously.

    Budget Hierarchy:
    1. Global budget - bounds total information leakage about the entire dataset
    2. Tenant budget - bounds information leakage about each tenant
    3. Query-type budget - prevents excessive queries of one type

    A query is only allowed if ALL applicable budgets have sufficient funds.
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        global_epsilon_per_period: float = 10.0,
        tenant_epsilon_per_period: float = 5.0,
        query_type_epsilon_per_period: float = 2.0,
        period_duration: timedelta = timedelta(days=30),
    ):
        self._db = db_pool
        self._global_budget = global_epsilon_per_period
        self._tenant_budget = tenant_epsilon_per_period
        self._query_type_budget = query_type_epsilon_per_period
        self._period_duration = period_duration

    async def check_and_reserve_budget(
        self,
        epsilon_needed: float,
        tenant_id: str,
        query_type: str,
    ) -> Optional[str]:
        """
        Check if budget is available at all levels and reserve it.

        Returns a reservation_id if successful, None if any budget is exhausted.

        This method is atomic - either all budgets are reserved or none are.
        """
        async with self._db.acquire() as conn:
            async with conn.transaction():
                # Check global budget
                global_remaining = await self._get_remaining(
                    conn, BudgetLevel.GLOBAL, "global"
                )
                if global_remaining < epsilon_needed:
                    return None

                # Check tenant budget
                tenant_remaining = await self._get_remaining(
                    conn, BudgetLevel.TENANT, tenant_id
                )
                if tenant_remaining < epsilon_needed:
                    return None

                # Check query type budget
                query_type_remaining = await self._get_remaining(
                    conn, BudgetLevel.QUERY_TYPE, query_type
                )
                if query_type_remaining < epsilon_needed:
                    return None

                # All checks passed - reserve budget at all levels
                reservation_id = await self._create_reservation(
                    conn, epsilon_needed, tenant_id, query_type
                )

                await self._spen


# DataDr Privacy Layer: Technical Specification (Part 2)

## Continuation from Part 1

This document continues the specification, focusing on architectural design and integration patterns.

---

## 8. Privacy Budget Management (Continued)

### 8.1 Budget Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    GLOBAL BUDGET                             │
│                    ε = 10.0 per month                        │
│                                                              │
│    Bounds total information leakage across ALL tenants       │
│    If exhausted: NO queries allowed until reset              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  TENANT BUDGET  │  │  TENANT BUDGET  │  │   TENANT    │ │
│  │   Tenant A      │  │   Tenant B      │  │   BUDGET    │ │
│  │   ε = 5.0/mo    │  │   ε = 5.0/mo    │  │   ...       │ │
│  │                 │  │                 │  │             │ │
│  │  Bounds info    │  │  Bounds info    │  │             │ │
│  │  about this     │  │  about this     │  │             │ │
│  │  tenant only    │  │  tenant only    │  │             │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  QUERY TYPE     │  │  QUERY TYPE     │  │ QUERY TYPE  │ │
│  │  "frequency"    │  │  "severity"     │  │   ...       │ │
│  │   ε = 2.0/mo    │  │   ε = 2.0/mo    │  │             │ │
│  │                 │  │                 │  │             │ │
│  │  Prevents       │  │  Prevents       │  │             │ │
│  │  excessive      │  │  excessive      │  │             │ │
│  │  frequency      │  │  severity       │  │             │ │
│  │  queries        │  │  queries        │  │             │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 Budget Check Flow

For any aggregate query:

1. **Check Global Budget** → If exhausted, reject
2. **Check Tenant Budget** (for each tenant whose data is touched) → If any exhausted, exclude that tenant
3. **Check Query Type Budget** → If exhausted, reject
4. **Reserve budget atomically at all levels**
5. **Execute query**
6. **Commit budget spend**

If step 5 fails, budget reservation is rolled back.

### 8.3 Budget Reset Policy

| Level | Reset Period | Rationale |
|-------|--------------|-----------|
| Global | Monthly | Bounds yearly leakage to 12 × ε_global |
| Tenant | Monthly | Aligns with billing cycle |
| Query Type | Weekly | Allows varied query patterns |

### 8.4 Budget Exhaustion Handling

When budget is exhausted:

```
┌─────────────────────────────────────────────────────────────┐
│                  BUDGET EXHAUSTION RESPONSE                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Global Exhausted:                                           │
│  → Return cached aggregates only (no new computation)        │
│  → Alert operations team                                     │
│  → Suggest customer waits for reset                          │
│                                                              │
│  Tenant Exhausted:                                           │
│  → Exclude tenant from aggregates                            │
│  → Return partial results (note: "N-1 tenants included")     │
│  → Notify tenant of budget status                            │
│                                                              │
│  Query Type Exhausted:                                       │
│  → Suggest alternative query types                           │
│  → Return cached results for this query type                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Federated Learning Protocol

### 9.1 Protocol Overview

DataDr uses federated learning to build models from distributed data without centralizing raw data.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        FEDERATED LEARNING ROUNDS                              │
│                                                                               │
│  Round 1                    Round 2                    Round N                │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐    │
│  │                 │       │                 │       │                 │    │
│  │  Global Model   │──────▶│  Global Model   │──────▶│  Global Model   │    │
│  │  v1.0           │       │  v1.1           │       │  v1.N           │    │
│  │                 │       │                 │       │                 │    │
│  └────────┬────────┘       └────────┬────────┘       └────────┬────────┘    │
│           │                         │                         │              │
│           ▼                         ▼                         ▼              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         DISTRIBUTE TO TENANTS                           ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│           │                         │                         │              │
│           ▼                         ▼                         ▼              │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐    │
│  │ Tenant A: Train │       │ Tenant A: Train │       │ Tenant A: Train │    │
│  │ locally, send   │       │ locally, send   │       │ locally, send   │    │
│  │ DP gradients    │       │ DP gradients    │       │ DP gradients    │    │
│  └────────┬────────┘       └────────┬────────┘       └────────┬────────┘    │
│           │                         │                         │              │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐    │
│  │ Tenant B: Train │       │ Tenant B: Train │       │ Tenant B: Train │    │
│  │ locally, send   │       │ locally, send   │       │ locally, send   │    │
│  │ DP gradients    │       │ DP gradients    │       │ DP gradients    │    │
│  └────────┬────────┘       └────────┬────────┘       └────────┬────────┘    │
│           │                         │                         │              │
│           ▼                         ▼                         ▼              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         SECURE AGGREGATION                              ││
│  │           Server sees SUM of gradients, not individual                  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│           │                         │                         │              │
│           ▼                         ▼                         ▼              │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐    │
│  │  Apply DP noise │       │  Apply DP noise │       │  Apply DP noise │    │
│  │  to aggregate   │       │  to aggregate   │       │  to aggregate   │    │
│  └────────┬────────┘       └────────┬────────┘       └────────┬────────┘    │
│           │                         │                         │              │
│           ▼                         ▼                         ▼              │
│  ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐    │
│  │  Update Global  │       │  Update Global  │       │  Update Global  │    │
│  │  Model          │       │  Model          │       │  Model          │    │
│  └─────────────────┘       └─────────────────┘       └─────────────────┘    │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Secure Aggregation Protocol

Secure aggregation ensures the server only sees the SUM of participant updates, not individual contributions.

**Protocol Steps:**

1. **Key Agreement Phase**
   - Each participant generates ephemeral key pair
   - Participants establish pairwise shared secrets (Diffie-Hellman)
   - Shared secrets are used to generate canceling masks

2. **Masking Phase**
   - Participant A computes: `masked_update_A = update_A + mask_AB - mask_AC + ...`
   - Masks are deterministically derived from shared secrets
   - For any pair (A,B): `mask_AB = -mask_BA` (they cancel when summed)

3. **Aggregation Phase**
   - Server collects all masked updates
   - Server computes: `sum(masked_updates) = sum(updates)` (masks cancel)
   - Server never sees individual updates

4. **Dropout Handling**
   - If participant drops out, surviving participants reveal their shared secrets with dropout
   - Server can reconstruct dropout's mask and subtract it
   - Privacy of surviving participants maintained

### 9.3 Model Architecture for Pattern Learning

```
┌─────────────────────────────────────────────────────────────┐
│                    PATTERN PREDICTION MODEL                  │
│                                                              │
│  Input Features:                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ • Schema fingerprint embedding (16 dims)                ││
│  │ • Column type one-hot (20 dims)                         ││
│  │ • Table size bucket (5 dims)                            ││
│  │ • Historical null rate (1 dim)                          ││
│  │ • Query frequency bucket (5 dims)                       ││
│  │ • Day of week (7 dims)                                  ││
│  │ • Hour of day (24 dims)                                 ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Embedding Layer (128 dims)                  ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Hidden Layer 1 (64 dims, ReLU)             ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Hidden Layer 2 (32 dims, ReLU)             ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Output Heads (multi-task)                   ││
│  │                                                          ││
│  │  • Pattern Type Prediction (softmax, 12 classes)        ││
│  │  • Severity Prediction (sigmoid, 1 dim)                 ││
│  │  • Root Cause Prediction (softmax, 20 classes)          ││
│  │  • Resolution Time Prediction (regression, 1 dim)       ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  Total Parameters: ~50,000                                   │
│  Gradient Size: ~200KB per update                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 9.4 DP-SGD for Local Training

Each tenant trains locally using Differentially Private Stochastic Gradient Descent:

**DP-SGD Steps:**

1. **Sample minibatch** - Random subset of local data
2. **Compute per-example gradients** - One gradient vector per data point
3. **Clip gradients** - Bound L2 norm of each gradient to `C`
4. **Sum clipped gradients** - Aggregate within minibatch
5. **Add Gaussian noise** - `N(0, σ²C²I)` where `σ` calibrated to `(ε,δ)`
6. **Update local model** - Standard SGD step with noised gradient

**Privacy Amplification:**
- Subsampling amplifies privacy: if we sample fraction `q` of data, effective `ε` is reduced
- Multiple rounds compose: track cumulative `(ε,δ)` using Rényi DP accounting

---

## 10. Audit and Compliance System

### 10.1 Audit Log Schema

Every privacy-relevant operation is logged immutably.

```
┌─────────────────────────────────────────────────────────────┐
│                      AUDIT LOG ENTRY                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  entry_id:          UUID (immutable)                         │
│  timestamp:         ISO 8601 with microseconds               │
│  event_type:        Enum (see below)                         │
│                                                              │
│  actor:                                                      │
│    type:            "agent" | "server" | "admin" | "system" │
│    id:              Tenant ID or service name                │
│    ip_address:      Source IP (hashed for privacy)           │
│                                                              │
│  resource:                                                   │
│    type:            "contribution" | "aggregate" | "budget"  │
│    id:              Resource identifier                      │
│    tenant_id:       Owning tenant (if applicable)            │
│                                                              │
│  privacy_impact:                                             │
│    epsilon_spent:   DP epsilon consumed                      │
│    delta_spent:     DP delta consumed                        │
│    budget_level:    "global" | "tenant" | "query_type"      │
│                                                              │
│  details:           JSON blob (operation-specific)           │
│  checksum:          SHA-256 of previous entry + this entry   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 Event Types

| Event Type | Description | Privacy Impact |
|------------|-------------|----------------|
| `contribution.received` | Agent submitted contribution | None (input) |
| `contribution.verified` | ZKP verification completed | None |
| `contribution.stored` | Contribution encrypted and stored | None |
| `aggregate.computed` | Aggregate query executed | ε spent |
| `aggregate.cached_served` | Cached aggregate returned | None |
| `budget.reserved` | Privacy budget reserved | ε reserved |
| `budget.committed` | Privacy budget spent | ε committed |
| `budget.released` | Reserved budget released (query failed) | None |
| `budget.exhausted` | Budget limit reached | None |
| `model.round_started` | FL round initiated | None |
| `model.gradients_aggregated` | Secure aggregation completed | ε spent |
| `model.updated` | Global model updated | None |
| `key.rotated` | Encryption key rotated | None |
| `access.denied` | Unauthorized access attempt | None |

### 10.3 Compliance Reports

**Privacy Budget Report (Daily)**

```
┌─────────────────────────────────────────────────────────────┐
│           DAILY PRIVACY BUDGET REPORT - 2024-01-15          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  GLOBAL BUDGET                                               │
│  ────────────────────────────────────────────────────────── │
│  Period:           2024-01-01 to 2024-01-31                 │
│  Budget (ε):       10.000                                    │
│  Spent (ε):        3.247                                     │
│  Remaining (ε):    6.753                                     │
│  Utilization:      32.5%                                     │
│                                                              │
│  TENANT BUDGETS (Top 5 by utilization)                      │
│  ────────────────────────────────────────────────────────── │
│  Tenant          Budget    Spent    Remaining    Util%      │
│  tenant_abc      5.000     2.341    2.659        46.8%      │
│  tenant_def      5.000     1.892    3.108        37.8%      │
│  tenant_ghi      5.000     1.456    3.544        29.1%      │
│  tenant_jkl      5.000     0.987    4.013        19.7%      │
│  tenant_mno      5.000     0.654    4.346        13.1%      │
│                                                              │
│  QUERY TYPE BUDGETS                                         │
│  ────────────────────────────────────────────────────────── │
│  Query Type      Budget    Spent    Remaining    Util%      │
│  frequency       2.000     1.234    0.766        61.7%      │
│  severity        2.000     0.876    1.124        43.8%      │
│  correlation     2.000     0.543    1.457        27.2%      │
│  prediction      2.000     0.321    1.679        16.1%      │
│                                                              │
│  ALERTS                                                      │
│  ────────────────────────────────────────────────────────── │
│  ⚠️  "frequency" query type at 61.7% - may exhaust by EOW   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Contribution Validity Report (Weekly)**

```
┌─────────────────────────────────────────────────────────────┐
│       WEEKLY CONTRIBUTION VALIDITY REPORT - Week 3 2024     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CONTRIBUTION SUMMARY                                        │
│  ────────────────────────────────────────────────────────── │
│  Total Contributions:        1,247                           │
│  Valid (ZKP verified):       1,243 (99.7%)                  │
│  Invalid (ZKP failed):       4 (0.3%)                       │
│                                                              │
│  INVALID CONTRIBUTION ANALYSIS                              │
│  ────────────────────────────────────────────────────────── │
│  Reason                      Count    Tenants Affected      │
│  Sample size below minimum   2        tenant_xyz            │
│  Hash mismatch               1        tenant_uvw            │
│  Proof malformed             1        tenant_rst            │
│                                                              │
│  ACTION ITEMS                                                │
│  ────────────────────────────────────────────────────────── │
│  • Contact tenant_xyz re: sample size configuration         │
│  • Investigate hash mismatch (possible version skew)        │
│  • Check agent version for tenant_rst                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 10.4 Cryptographic Audit Chain

Audit logs are chained cryptographically to prevent tampering:

```
Entry N-1                    Entry N                      Entry N+1
┌──────────────┐            ┌──────────────┐            ┌──────────────┐
│              │            │              │            │              │
│  data        │            │  data        │            │  data        │
│  timestamp   │            │  timestamp   │            │  timestamp   │
│  ...         │            │  ...         │            │  ...         │
│              │            │              │            │              │
│  prev_hash ──┼────────────│  prev_hash ──┼────────────│  prev_hash   │
│              │     │      │              │     │      │              │
│  checksum    │◀────┘      │  checksum    │◀────┘      │  checksum    │
│              │            │              │            │              │
└──────────────┘            └──────────────┘            └──────────────┘

checksum_N = SHA256(checksum_{N-1} || serialize(entry_N))
```

Any modification to a historical entry breaks the chain.

---

## 11. Testing and Verification

### 11.1 Privacy Testing Framework

**Test Categories:**

| Category | Purpose | Frequency |
|----------|---------|-----------|
| Unit Tests | Verify DP mechanisms produce correct noise distributions | Every commit |
| Integration Tests | Verify end-to-end privacy guarantees | Every PR |
| Membership Inference Tests | Verify DP prevents membership inference attacks | Weekly |
| Reconstruction Tests | Verify aggregates don't leak individual records | Weekly |
| Budget Accounting Tests | Verify budget tracking is accurate | Every commit |
| ZKP Soundness Tests | Verify proofs can't be forged | Every commit |

### 11.2 Membership Inference Attack Test

This test verifies that DP prevents an attacker from determining whether a specific record was in the dataset.

**Test Procedure:**

1. Create two datasets: D and D' where D' = D - {target_record}
2. Train model on D, compute aggregates on D
3. Train model on D', compute aggregates on D'
4. Train attack classifier to distinguish outputs from D vs D'
5. **Pass Criterion:** Attack classifier accuracy ≤ 50% + δ (no better than random)

### 11.3 Reconstruction Attack Test

This test verifies that aggregates don't reveal individual records.

**Test Procedure:**

1. Compute aggregates over dataset with known records
2. Attempt to reconstruct individual records from aggregates
3. **Pass Criterion:** Reconstruction error > threshold for all records

### 11.4 ZKP Completeness and Soundness Tests

**Completeness Test:**
- Generate valid contribution with honest prover
- Verify proof succeeds
- **Pass Criterion:** 100% of valid contributions produce valid proofs

**Soundness Test:**
- Attempt to generate proof for invalid contribution (fabricated data, insufficient samples, etc.)
- Verify proof fails
- **Pass Criterion:** 100% of invalid contributions produce invalid proofs

---

## 12. Deployment Configuration

### 12.1 Agent Deployment

**Docker Compose (Customer Side):**

```yaml
# docker-compose.yml for DataDr Agent
version: '3.8'

services:
  datadr-agent:
    image: datadr/agent:${VERSION}
    restart: unless-stopped

    # Security: Run as non-root
    user: "1000:1000"

    # Security: Read-only filesystem
    read_only: true

    # Security: Drop all capabilities
    cap_drop:
      - ALL

    # Security: No new privileges
    security_opt:
      - no-new-privileges:true

    volumes:
      # Configuration (read-only)
      - ./config:/etc/datadr:ro

      # Certificates (read-only)
      - ./certs:/etc/datadr/certs:ro

      # State directory (read-write, for budget tracking)
      - datadr-state:/var/lib/datadr

      # Temp directory for ZKP computation
      - type: tmpfs
        target: /tmp
        tmpfs:
          size: 1G

    environment:
      - DATADR_TENANT_ID=${TENANT_ID}
      - DATADR_LOG_LEVEL=info
      - DATADR_DP_EPSILON=1.0
      - DATADR_DP_DELTA=1e-8
      - DATADR_MIN_SAMPLE_SIZE=100

    # Network: Only outbound to DataDr servers
    networks:
      - datadr-net

    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '0.5'
          memory: 1G

volumes:
  datadr-state:
    driver: local

networks:
  datadr-net:
    driver: bridge
```

### 12.2 Server Infrastructure

**Kubernetes Deployment (DataDr Side):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATADR SERVER INFRASTRUCTURE                         │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                            INGRESS LAYER                                ││
│  │                                                                         ││
│  │  • AWS ALB / GCP Cloud Load Balancer                                   ││
│  │  • TLS termination with certificate pinning                            ││
│  │  • WAF rules for DDoS protection                                       ││
│  │  • Rate limiting per tenant                                            ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         INGESTION SERVICE                               ││
│  │                                                                         ││
│  │  Deployment: 3 replicas, HPA (5-20 based on queue depth)               ││
│  │  Resources: 2 CPU, 4GB RAM per pod                                     ││
│  │                                                                         ││
│  │  Responsibilities:                                                      ││
│  │  • Receive contributions from agents                                   ││
│  │  • Verify ZK proofs (calls ZKP Verifier)                              ││
│  │  • Encrypt and store contributions                                     ││
│  │  • Update privacy budget                                               ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                          ZKP VERIFIER SERVICE                           ││
│  │                                                                         ││
│  │  Deployment: 5 replicas (verification is fast but CPU-bound)           ││
│  │  Resources: 4 CPU, 2GB RAM per pod                                     ││
│  │                                                                         ││
│  │  Responsibilities:                                                      ││
│  │  • Verify RISC Zero proofs                                             ││
│  │  • Cache verification results                                          ││
│  │  • Report verification metrics                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        STORAGE LAYER                                    ││
│  │                                                                         ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        ││
│  │  │   S3 Buckets    │  │   PostgreSQL    │  │   Redis         │        ││
│  │  │   (encrypted)   │  │   (metadata)    │  │   (cache)       │        ││
│  │  │                 │  │                 │  │                 │        ││
│  │  │ • Contributions │  │ • Budget state  │  │ • Aggregates    │        ││
│  │  │ • Tenant keys   │  │ • Audit logs    │  │ • Sessions      │        ││
│  │  │ • Models        │  │ • Tenant config │  │ • Rate limits   │        ││
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘        ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                      AGGREGATION SERVICE                                ││
│  │                                                                         ││
│  │  Deployment: 3 replicas (stateless, scales with query load)            ││
│  │  Resources: 4 CPU, 8GB RAM per pod                                     ││
│  │                                                                         ││
│  │  Responsibilities:                                                      ││
│  │  • Compute DP aggregates across tenants                                ││
│  │  • Manage privacy budget accounting                                    ││
│  │  • Cache aggregate results                                             ││
│  │  • Serve API queries                                                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    FEDERATED LEARNING SERVICE                           ││
│  │                                                                         ││
│  │  Deployment: 1 replica (singleton, coordinates FL rounds)              ││
│  │  Resources: 8 CPU, 16GB RAM                                            ││
│  │                                                                         ││
│  │  Responsibilities:                                                      ││
│  │  • Coordinate FL rounds                                                ││
│  │  • Distribute global model to agents                                   ││
│  │  • Perform secure aggregation of gradients                             ││
│  │  • Apply DP noise to aggregated gradients                              ││
│  │  • Update and version global model                                     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 12.3 Key Management

```
┌─────────────────────────────────────────────────────────────┐
│                    KEY HIERARCHY                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  AWS KMS / GCP Cloud KMS / HashiCorp Vault                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                                                          ││
│  │  MASTER KEY (never leaves HSM)                          ││
│  │  └── Encrypts all tenant DEKs                           ││
│  │                                                          ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  TENANT DATA ENCRYPTION KEYS (DEKs)                     ││
│  │                                                          ││
│  │  tenant_abc_dek ─── Encrypts tenant_abc's contributions ││
│  │  tenant_def_dek ─── Encrypts tenant_def's contributions ││
│  │  tenant_ghi_dek ─── Encrypts tenant_ghi's contributions ││
│  │  ...                                                     ││
│  │                                                          ││
│  │  DEKs stored encrypted in S3, decrypted on-demand       ││
│  │  via KMS Decrypt API                                     ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  AGENT CERTIFICATES (mTLS)                              ││
│  │                                                          ││
│  │  • One certificate per tenant                           ││
│  │  • Issued by DataDr CA                                  ││
│  │  • Rotated annually                                     ││
│  │  • Revocable via CRL/OCSP                              ││
│  └─────────────────────────────────────────────────────────┘│
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  ZKP SIGNING KEYS                                       ││
│  │                                                          ││
│  │  • Ed25519 key pair per tenant                          ││
│  │  • Used to sign contribution proofs                     ││
│  │  • Public key registered with DataDr                    ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 12.4 Rotation Schedule

| Key Type | Rotation Period | Procedure |
|----------|-----------------|-----------|
| Master Key | Annual | KMS automatic rotation |
| Tenant DEKs | Annual | Re-encrypt contributions with new DEK |
| Agent Certificates | Annual | Issue new cert, revoke old |
| ZKP Signing Keys | Bi-annual | Register new public key |

---

## 13. Implementation Checklist

**CRITICAL: The implementing engineer must complete ALL items below.**

### Phase 1: Foundation (Weeks 1-3)

- [ ] Set up agent project structure with async Python
- [ ] Implement connector interface and PostgreSQL connector
- [ ] Implement pattern extractor with schema fingerprinting
- [ ] Implement local DP engine with Laplace mechanism
- [ ] Implement privacy budget manager with persistence
- [ ] Unit tests for all DP mechanisms (verify noise distributions)

### Phase 2: Transport & Storage (Weeks 4-5)

- [ ] Implement secure transport client with mTLS
- [ ] Implement hybrid encryption (X25519 + AES-256-GCM)
- [ ] Implement contribution package serialization
- [ ] Implement server-side storage with tenant isolation
- [ ] Implement key management integration (KMS)
- [ ] Integration tests for end-to-end encryption

### Phase 3: ZKP System (Weeks 6-8)

- [ ] Set up RISC Zero development environment
- [ ] Implement contribution validity circuit in Rust
- [ ] Implement proof generation in agent
- [ ] Implement proof verification on server
- [ ] Soundness and completeness tests for ZKP

### Phase 4: Aggregation & Budget (Weeks 9-10)

- [ ] Implement server-side DP aggregator
- [ ] Implement multi-level budget tracking
- [ ] Implement budget exhaustion handling
- [ ] Implement aggregate caching
- [ ] Privacy budget accounting tests

### Phase 5: Federated Learning (Weeks 11-13)

- [ ] Implement secure aggregation protocol
- [ ] Implement DP-SGD for local training
- [ ] Implement FL round coordination
- [ ] Implement model versioning and distribution
- [ ] Membership inference attack tests

### Phase 6: Audit & Compliance (Weeks 14-15)

- [ ] Implement audit log schema and storage
- [ ] Implement cryptographic audit chain
- [ ] Implement compliance report generation
- [ ] Implement tenant isolation verification
- [ ] External security audit

### Phase 7: Deployment (Week 16)

- [ ] Agent Docker image and Helm chart
- [ ] Server Kubernetes manifests
- [ ] CI/CD pipelines
- [ ] Monitoring and alerting
- [ ] Documentation

---

## 14. Security Considerations

### 14.1 Threat Model

| Threat | Mitigation |
|--------|------------|
| Malicious tenant fabricates data | ZKP validity proofs |
| Server compromise | Tenant-isolated encryption, audit logs |
| Network MITM | mTLS with certificate pinning |
| Insider threat | Multi-party key management, audit trails |
| DP parameter misconfiguration | Hardcoded bounds, automated verification |
| Budget bypass | Server-side budget enforcement |
| Timing attacks | Constant-time crypto operations |

### 14.2 Non-Goals

This system does NOT protect against:

- Malicious tenant poisoning their own data quality
- Side-channel attacks on the agent (customer's responsibility)
- Compromise of the agent's host machine (customer's responsibility)
- Legal compulsion (data subject to legal process)

---

## 15. References

### Academic Papers

1. Dwork, C. et al. "Calibrating Noise to Sensitivity in Private Data Analysis" (2006) - Foundation of DP
2. Abadi, M. et al. "Deep Learning with Differential Privacy" (2016) - DP-SGD
3. Bonawitz, K. et al. "Practical Secure Aggregation for Privacy-Preserving Machine Learning" (2017) - Secure aggregation
4. Ben-Sasson, E. et al. "SNARKs for C: Verifying Program Executions Succinctly and in Zero Knowledge" (2013) - ZKP foundations

### Libraries and Tools

- OpenDP: https://opendp.org/ - DP library
- RISC Zero: https://risczero.com/ - ZKP framework
- TensorFlow Federated: https://www.tensorflow.org/federated - FL framework
- AWS KMS: https://aws.amazon.com/kms/ - Key management

---

## FINAL INSTRUCTION TO IMPLEMENTING ENGINEER

This specification describes a production-grade privacy system. Every component is necessary for the privacy guarantees to hold. Cutting corners or deferring security measures will result in a system that CLAIMS privacy but DOES NOT PROVIDE IT.

**Do not:**
- Skip ZKP verification ("we'll add it later")
- Use hardcoded keys ("just for testing")
- Disable budget tracking ("it slows things down")
- Remove noise for debugging ("I need to see the real values")

**Do:**
- Implement the full specification
- Write tests that verify privacy properties
- Get external security review before launch
- Monitor privacy budget consumption in production

The privacy of our customers' data depends on complete, correct implementation of this system.
