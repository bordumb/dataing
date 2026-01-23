"""Investigation starter service for Temporal-based investigations.

This module provides a centralized service for starting investigations,
ensuring consistent behavior across all entry points (API routes, integrations, etc.).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase
    from dataing.temporal.client import TemporalInvestigationClient

logger = structlog.get_logger()


@dataclass
class StartInvestigationResult:
    """Result from starting an investigation."""

    investigation_id: UUID
    status: str


class InvestigationStarterService:
    """Service for starting Temporal investigations.

    Centralizes the logic for creating investigation records and starting
    Temporal workflows, ensuring DRY across all entry points.
    """

    def __init__(
        self,
        db: AppDatabase,
        temporal_client: TemporalInvestigationClient | None = None,
    ) -> None:
        """Initialize the investigation service."""
        self.db = db
        self.temporal_client = temporal_client

    async def start_investigation(
        self,
        *,
        tenant_id: UUID,
        datasource_id: UUID,
        alert_data: dict[str, Any],
        alert_summary: str,
        created_by: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> StartInvestigationResult:
        """Start a new investigation with Temporal workflow.

        This method:
        1. Creates the investigation record in the database
        2. Starts the Temporal workflow for processing

        Args:
            tenant_id: The tenant ID.
            datasource_id: The datasource to investigate.
            alert_data: Alert data containing investigation context.
            alert_summary: Human-readable summary of the alert.
            created_by: Optional user ID who created the investigation.
            investigation_id: Optional pre-generated investigation ID.

        Returns:
            StartInvestigationResult with the investigation ID and status.

        Raises:
            RuntimeError: If Temporal client is not configured.
            Exception: If database insert or workflow start fails.
        """
        if self.temporal_client is None:
            raise RuntimeError("Temporal client not configured")

        # Generate ID if not provided
        if investigation_id is None:
            investigation_id = uuid4()

        # Ensure datasource_id is in alert_data
        alert_data_with_ds = {**alert_data, "datasource_id": str(datasource_id)}

        # Create database record
        await self.db.execute(
            """
            INSERT INTO investigations (id, tenant_id, alert, created_by)
            VALUES ($1, $2, $3, $4)
            """,
            investigation_id,
            tenant_id,
            json.dumps(alert_data_with_ds),
            created_by,
        )

        # Start Temporal workflow
        await self.temporal_client.start_investigation(
            investigation_id=str(investigation_id),
            tenant_id=str(tenant_id),
            datasource_id=str(datasource_id),
            alert_data=alert_data_with_ds,
            alert_summary=alert_summary,
        )

        logger.info(
            "investigation_started",
            investigation_id=str(investigation_id),
            tenant_id=str(tenant_id),
            datasource_id=str(datasource_id),
            created_by=str(created_by) if created_by else None,
        )

        return StartInvestigationResult(
            investigation_id=investigation_id,
            status="queued",
        )
