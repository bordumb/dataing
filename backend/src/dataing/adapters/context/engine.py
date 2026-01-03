"""Default Context Engine - Gathers investigation context.

This module implements the ContextEngine protocol,
gathering schema and lineage information for investigations.

FAIL FAST: If schema discovery fails or returns no tables,
the engine raises SchemaDiscoveryError immediately.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from dataing.core.domain_types import InvestigationContext
from dataing.core.exceptions import SchemaDiscoveryError

if TYPE_CHECKING:
    from dataing.core.domain_types import AnomalyAlert
    from dataing.core.interfaces import DatabaseAdapter
    from .lineage import OpenLineageClient

logger = structlog.get_logger()


class DefaultContextEngine:
    """Gathers all context needed for investigation.

    FAIL FAST: Raises SchemaDiscoveryError if schema is empty.

    This engine gathers:
    1. Database schema (REQUIRED - fails if empty)
    2. Data lineage (OPTIONAL - graceful degradation)

    Attributes:
        db: Database adapter for schema discovery.
        lineage_client: Optional lineage client.
    """

    def __init__(
        self,
        db: DatabaseAdapter,
        lineage_client: OpenLineageClient | None = None,
    ) -> None:
        """Initialize the context engine.

        Args:
            db: Database adapter for schema discovery.
            lineage_client: Optional client for lineage discovery.
        """
        self.db = db
        self.lineage_client = lineage_client

    async def gather(self, alert: AnomalyAlert) -> InvestigationContext:
        """Gather schema and lineage context.

        Args:
            alert: The anomaly alert being investigated.

        Returns:
            InvestigationContext with schema and optional lineage.

        Raises:
            SchemaDiscoveryError: If no tables discovered.
        """
        log = logger.bind(dataset=alert.dataset_id)

        # 1. Schema Discovery (REQUIRED)
        log.info("Discovering schema")
        try:
            schema = await self.db.get_schema()
        except Exception as e:
            log.error("Schema discovery failed", error=str(e))
            raise SchemaDiscoveryError(f"Failed to discover schema: {e}") from e

        if not schema.tables:
            log.error("No tables discovered")
            raise SchemaDiscoveryError(
                "No tables discovered. "
                "Check database connectivity and permissions. "
                "Investigation cannot proceed without schema."
            )

        log.info("Schema discovered", tables_count=len(schema.tables))

        # 2. Lineage Discovery (OPTIONAL - graceful degradation)
        lineage = None
        if self.lineage_client:
            try:
                log.info("Discovering lineage")
                lineage = await self.lineage_client.get_lineage(alert.dataset_id)
                log.info(
                    "Lineage discovered",
                    upstream_count=len(lineage.upstream),
                    downstream_count=len(lineage.downstream),
                )
            except Exception as e:
                # Log but don't fail - lineage is optional
                log.warning(
                    "Lineage discovery failed, proceeding without",
                    error=str(e),
                    dataset=alert.dataset_id,
                )

        return InvestigationContext(schema=schema, lineage=lineage)
