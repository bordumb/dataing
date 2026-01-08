"""Repository for training signal persistence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from .types import TrainingSignal

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()

# Keep TrainingSignal imported for external use
__all__ = ["TrainingSignalRepository", "TrainingSignal"]


class TrainingSignalRepository:
    """Repository for persisting training signals.

    Attributes:
        db: Application database for storing signals.
    """

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository.

        Args:
            db: Application database connection.
        """
        self.db = db

    async def record_signal(
        self,
        signal_type: str,
        tenant_id: UUID,
        investigation_id: UUID,
        input_context: dict[str, Any],
        output_response: dict[str, Any],
        automated_score: float | None = None,
        automated_dimensions: dict[str, float] | None = None,
        model_version: str | None = None,
        source_event_id: UUID | None = None,
    ) -> UUID:
        """Record a training signal.

        Args:
            signal_type: Type of output (interpretation, synthesis).
            tenant_id: Tenant identifier.
            investigation_id: Investigation identifier.
            input_context: Context provided to LLM.
            output_response: Response from LLM.
            automated_score: Composite score from validator.
            automated_dimensions: Dimensional scores.
            model_version: Model version string.
            source_event_id: Optional link to feedback event.

        Returns:
            UUID of the created signal.
        """
        signal_id = uuid4()

        query = """
            INSERT INTO rl_training_signals (
                id, signal_type, tenant_id, investigation_id,
                input_context, output_response,
                automated_score, automated_dimensions,
                model_version, source_event_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """

        await self.db.execute(
            query,
            signal_id,
            signal_type,
            tenant_id,
            investigation_id,
            json.dumps(input_context),
            json.dumps(output_response),
            automated_score,
            json.dumps(automated_dimensions) if automated_dimensions else None,
            model_version,
            source_event_id,
        )

        logger.debug(
            f"training_signal_recorded signal_id={signal_id} "
            f"signal_type={signal_type} investigation_id={investigation_id}"
        )

        return signal_id

    async def update_human_feedback(
        self,
        investigation_id: UUID,
        signal_type: str,
        score: float,
    ) -> None:
        """Update signal with human feedback score.

        Args:
            investigation_id: Investigation to update.
            signal_type: Type of signal to update.
            score: Human feedback score (-1, 0, or 1).
        """
        query = """
            UPDATE rl_training_signals
            SET human_feedback_score = $1
            WHERE investigation_id = $2 AND signal_type = $3
        """

        await self.db.execute(query, score, investigation_id, signal_type)

        logger.debug(
            f"human_feedback_updated investigation_id={investigation_id} "
            f"signal_type={signal_type} score={score}"
        )

    async def update_outcome_score(
        self,
        investigation_id: UUID,
        score: float,
    ) -> None:
        """Update signal with outcome score.

        Args:
            investigation_id: Investigation to update.
            score: Outcome score (0.0-1.0).
        """
        query = """
            UPDATE rl_training_signals
            SET outcome_score = $1
            WHERE investigation_id = $2
        """

        await self.db.execute(query, score, investigation_id)

        logger.debug(f"outcome_score_updated investigation_id={investigation_id} score={score}")
