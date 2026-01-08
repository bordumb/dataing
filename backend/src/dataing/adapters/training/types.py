"""Types for training signal capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class TrainingSignal:
    """Training signal for RL pipeline.

    Attributes:
        id: Unique signal identifier.
        signal_type: Type of LLM output (interpretation, synthesis).
        tenant_id: Tenant this signal belongs to.
        investigation_id: Investigation this signal relates to.
        input_context: Context provided to the LLM.
        output_response: Response from the LLM.
        automated_score: Composite score from validator.
        automated_dimensions: Dimensional scores.
        model_version: Version of the model that produced the output.
        created_at: When the signal was created.
    """

    signal_type: str
    tenant_id: UUID
    investigation_id: UUID
    input_context: dict[str, Any]
    output_response: dict[str, Any]
    automated_score: float | None = None
    automated_dimensions: dict[str, float] | None = None
    model_version: str | None = None
    source_event_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
