"""Context Engine - Thin coordinator for investigation context gathering.

This module orchestrates the various context modules to gather
all information needed for an investigation. It's a thin coordinator
that delegates to specialized modules.

Uses the unified SchemaResponse from the datasource layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from dataing.adapters.datasource.types import SchemaResponse
from dataing.adapters.lineage import DatasetId, LineageAdapter
from dataing.core.domain_types import InvestigationContext, LineageContext
from dataing.core.exceptions import SchemaDiscoveryError

from .anomaly_context import AnomalyConfirmation, AnomalyContext
from .correlation_context import Correlation, CorrelationContext
from .schema_context import SchemaContextBuilder

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.datasource.sql.base import SQLAdapter
    from dataing.core.domain_types import AnomalyAlert

logger = structlog.get_logger()


@dataclass
class EnrichedContext:
    """Extended context with anomaly confirmation and correlations.

    Attributes:
        base: The base investigation context (schema + lineage).
        anomaly_confirmed: Whether the anomaly was verified in data.
        confirmation: Anomaly confirmation details.
        correlations: Cross-table correlations found.
        schema_formatted: Schema formatted for LLM prompt.
    """

    base: InvestigationContext
    anomaly_confirmed: bool
    confirmation: AnomalyConfirmation | None
    correlations: list[Correlation]
    schema_formatted: str


class ContextEngine:
    """Thin coordinator for context gathering.

    This class orchestrates the specialized context modules:
    - SchemaContextBuilder: Schema discovery and formatting
    - AnomalyContext: Anomaly confirmation
    - CorrelationContext: Cross-table pattern detection
    """

    def __init__(
        self,
        schema_builder: SchemaContextBuilder | None = None,
        anomaly_ctx: AnomalyContext | None = None,
        correlation_ctx: CorrelationContext | None = None,
        lineage_adapter: LineageAdapter | None = None,
    ) -> None:
        """Initialize the context engine.

        Args:
            schema_builder: Schema context builder (created if None).
            anomaly_ctx: Anomaly context (created if None).
            correlation_ctx: Correlation context (created if None).
            lineage_adapter: Optional lineage adapter for fetching lineage.
        """
        self.schema_builder = schema_builder or SchemaContextBuilder()
        self.anomaly_ctx = anomaly_ctx or AnomalyContext()
        self.correlation_ctx = correlation_ctx or CorrelationContext()
        self.lineage_adapter = lineage_adapter

    def _count_tables(self, schema: SchemaResponse) -> int:
        """Count total tables in a schema response."""
        return sum(
            len(db_schema.tables) for catalog in schema.catalogs for db_schema in catalog.schemas
        )

    async def gather(
        self,
        alert: AnomalyAlert,
        adapter: BaseAdapter,
    ) -> InvestigationContext:
        """Gather schema and lineage context.

        Args:
            alert: The anomaly alert being investigated.
            adapter: Connected data source adapter.

        Returns:
            InvestigationContext with schema and optional lineage.

        Raises:
            SchemaDiscoveryError: If no tables discovered.
        """
        log = logger.bind(dataset=alert.dataset_id)
        log.info("gathering_context")

        # 1. Schema Discovery (REQUIRED)
        try:
            schema = await self.schema_builder.build(adapter)
        except Exception as e:
            log.error("schema_discovery_failed", error=str(e))
            raise SchemaDiscoveryError(f"Failed to discover schema: {e}") from e

        table_count = self._count_tables(schema)
        if table_count == 0:
            log.error("no_tables_discovered")
            raise SchemaDiscoveryError(
                "No tables discovered. "
                "Check database connectivity and permissions. "
                "Investigation cannot proceed without schema."
            )

        log.info("schema_discovered", tables_count=table_count)

        # 2. Lineage Discovery (OPTIONAL)
        lineage = None
        if self.lineage_adapter:
            try:
                log.info("discovering_lineage")
                lineage = await self._fetch_lineage(alert.dataset_id)
                log.info(
                    "lineage_discovered",
                    upstream_count=len(lineage.upstream),
                    downstream_count=len(lineage.downstream),
                )
            except Exception as e:
                log.warning("lineage_discovery_failed", error=str(e))

        return InvestigationContext(schema=schema, lineage=lineage)

    async def _fetch_lineage(self, dataset_id_str: str) -> LineageContext:
        """Fetch lineage using the lineage adapter and convert to LineageContext.

        Args:
            dataset_id_str: Dataset identifier as a string.

        Returns:
            LineageContext with upstream and downstream dependencies.
        """
        if not self.lineage_adapter:
            return LineageContext(target=dataset_id_str, upstream=(), downstream=())

        # Parse the dataset_id string into a DatasetId
        dataset_id = self._parse_dataset_id(dataset_id_str)

        # Fetch upstream and downstream with depth=1 for direct dependencies
        upstream_datasets = await self.lineage_adapter.get_upstream(dataset_id, depth=1)
        downstream_datasets = await self.lineage_adapter.get_downstream(dataset_id, depth=1)

        # Convert to simple string tuples for LineageContext
        upstream_names = tuple(ds.qualified_name for ds in upstream_datasets)
        downstream_names = tuple(ds.qualified_name for ds in downstream_datasets)

        return LineageContext(
            target=dataset_id_str,
            upstream=upstream_names,
            downstream=downstream_names,
        )

    def _parse_dataset_id(self, dataset_id_str: str) -> DatasetId:
        """Parse a dataset ID string into a DatasetId object.

        Handles various formats:
        - "schema.table" -> platform="unknown", name="schema.table"
        - "snowflake://db.schema.table" -> platform="snowflake", name="db.schema.table"
        - DataHub URN format

        Args:
            dataset_id_str: Dataset identifier string.

        Returns:
            DatasetId object.
        """
        return DatasetId.from_urn(dataset_id_str)

    async def gather_enriched(
        self,
        alert: AnomalyAlert,
        adapter: SQLAdapter,
    ) -> EnrichedContext:
        """Gather enriched context with anomaly confirmation.

        This extended method provides additional context including
        anomaly confirmation and cross-table correlations.

        Args:
            alert: The anomaly alert being investigated.
            adapter: Connected data source adapter.

        Returns:
            EnrichedContext with all available context.

        Raises:
            SchemaDiscoveryError: If no tables discovered.
        """
        log = logger.bind(dataset=alert.dataset_id)
        log.info("gathering_enriched_context")

        # 1. Get base context (schema + lineage)
        base = await self.gather(alert, adapter)

        # 2. Confirm anomaly in data
        log.info("confirming_anomaly")
        try:
            confirmation = await self.anomaly_ctx.confirm(adapter, alert)
            anomaly_confirmed = confirmation.exists
            log.info("anomaly_confirmation", confirmed=anomaly_confirmed)
        except Exception as e:
            log.warning("anomaly_confirmation_failed", error=str(e))
            confirmation = None
            anomaly_confirmed = False

        # 3. Find correlations
        log.info("finding_correlations")
        try:
            correlations = await self.correlation_ctx.find_correlations(adapter, alert, base.schema)
            log.info("correlations_found", count=len(correlations))
        except Exception as e:
            log.warning("correlation_analysis_failed", error=str(e))
            correlations = []

        # 4. Format schema for LLM
        schema_formatted = self.schema_builder.format_for_llm(base.schema)

        return EnrichedContext(
            base=base,
            anomaly_confirmed=anomaly_confirmed,
            confirmation=confirmation,
            correlations=correlations,
            schema_formatted=schema_formatted,
        )


# Backward compatibility alias
DefaultContextEngine = ContextEngine
