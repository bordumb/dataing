"""Context Engine - Thin coordinator for investigation context gathering.

This module orchestrates the various context modules to gather
all information needed for an investigation. It's a thin coordinator
that delegates to specialized modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from dataing.core.domain_types import InvestigationContext
from dataing.core.exceptions import SchemaDiscoveryError

from .anomaly_context import AnomalyConfirmation, AnomalyContext
from .correlation_context import Correlation, CorrelationContext
from .schema_context import SchemaContextBuilder

if TYPE_CHECKING:
    from dataing.core.domain_types import AnomalyAlert
    from dataing.core.interfaces import DatabaseAdapter

    from .lineage import OpenLineageClient

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

    It maintains backward compatibility with the existing
    DefaultContextEngine interface while adding new capabilities.
    """

    def __init__(
        self,
        schema_builder: SchemaContextBuilder | None = None,
        anomaly_ctx: AnomalyContext | None = None,
        correlation_ctx: CorrelationContext | None = None,
        lineage_client: OpenLineageClient | None = None,
    ) -> None:
        """Initialize the context engine.

        Args:
            schema_builder: Schema context builder (created if None).
            anomaly_ctx: Anomaly context (created if None).
            correlation_ctx: Correlation context (created if None).
            lineage_client: Optional lineage client.
        """
        self.schema_builder = schema_builder or SchemaContextBuilder()
        self.anomaly_ctx = anomaly_ctx or AnomalyContext()
        self.correlation_ctx = correlation_ctx or CorrelationContext()
        self.lineage_client = lineage_client

    async def gather(
        self,
        alert: AnomalyAlert,
        adapter: DatabaseAdapter,
    ) -> InvestigationContext:
        """Gather schema and lineage context.

        This method maintains backward compatibility with the
        existing DefaultContextEngine.gather() interface.

        Args:
            alert: The anomaly alert being investigated.
            adapter: Connected database adapter.

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

        if not schema.tables:
            log.error("no_tables_discovered")
            raise SchemaDiscoveryError(
                "No tables discovered. "
                "Check database connectivity and permissions. "
                "Investigation cannot proceed without schema."
            )

        log.info("schema_discovered", tables_count=len(schema.tables))

        # 2. Lineage Discovery (OPTIONAL)
        lineage = None
        if self.lineage_client:
            try:
                log.info("discovering_lineage")
                lineage = await self.lineage_client.get_lineage(alert.dataset_id)
                log.info(
                    "lineage_discovered",
                    upstream_count=len(lineage.upstream),
                    downstream_count=len(lineage.downstream),
                )
            except Exception as e:
                log.warning("lineage_discovery_failed", error=str(e))

        return InvestigationContext(schema=schema, lineage=lineage)

    async def gather_enriched(
        self,
        alert: AnomalyAlert,
        adapter: DatabaseAdapter,
    ) -> EnrichedContext:
        """Gather enriched context with anomaly confirmation.

        This extended method provides additional context including
        anomaly confirmation and cross-table correlations.

        Args:
            alert: The anomaly alert being investigated.
            adapter: Connected database adapter.

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
