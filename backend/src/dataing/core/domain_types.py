"""Domain types - Immutable Pydantic models defining core domain objects.

This module contains all the core data structures used throughout the
investigation system. All models are frozen (immutable) to ensure
data integrity and thread safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dataing.adapters.datasource.types import SchemaResponse


class AnomalyAlert(BaseModel):
    """Input: The anomaly that triggered the investigation.

    Attributes:
        dataset_id: The affected table in "schema.table_name" format.
        metric_name: The metric that deviated (e.g., "row_count", "null_rate").
        expected_value: The expected metric value based on historical data.
        actual_value: The actual observed metric value.
        deviation_pct: Percentage deviation from expected.
        anomaly_date: Date of the anomaly in "YYYY-MM-DD" format.
        severity: Alert severity level.
        metadata: Optional additional context.
    """

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_pct: float
    anomaly_date: str
    severity: str
    metadata: dict[str, str | int | float | bool] | None = None


class HypothesisCategory(str, Enum):
    """Categories of potential root causes for anomalies."""

    UPSTREAM_DEPENDENCY = "upstream_dependency"
    TRANSFORMATION_BUG = "transformation_bug"
    DATA_QUALITY = "data_quality"
    INFRASTRUCTURE = "infrastructure"
    EXPECTED_VARIANCE = "expected_variance"


class Hypothesis(BaseModel):
    """A potential explanation for the anomaly.

    Attributes:
        id: Unique identifier for this hypothesis.
        title: Short descriptive title.
        category: Classification of the hypothesis type.
        reasoning: Explanation of why this could be the cause.
        suggested_query: SQL query to investigate this hypothesis.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    category: HypothesisCategory
    reasoning: str
    suggested_query: str


class Evidence(BaseModel):
    """Result of executing a query to test a hypothesis.

    Attributes:
        hypothesis_id: ID of the hypothesis being tested.
        query: The SQL query that was executed.
        result_summary: Truncated/sampled results for display.
        row_count: Number of rows returned.
        supports_hypothesis: Whether evidence supports the hypothesis.
        confidence: Confidence score from 0.0 to 1.0.
        interpretation: Human-readable interpretation of results.
    """

    model_config = ConfigDict(frozen=True)

    hypothesis_id: str
    query: str
    result_summary: str
    row_count: int
    supports_hypothesis: bool | None
    confidence: float
    interpretation: str


class Finding(BaseModel):
    """The final output of an investigation.

    Attributes:
        investigation_id: ID of the investigation.
        status: Final status (completed, failed, inconclusive).
        root_cause: Identified root cause, if found.
        confidence: Confidence in the finding from 0.0 to 1.0.
        evidence: All evidence collected during investigation.
        recommendations: Suggested remediation actions.
        duration_seconds: Total investigation duration.
    """

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    status: str
    root_cause: str | None
    confidence: float
    evidence: list[Evidence]
    recommendations: list[str]
    duration_seconds: float


@dataclass(frozen=True)
class LineageContext:
    """Upstream and downstream dependencies for a dataset.

    Attributes:
        target: The target table being investigated.
        upstream: Tables that feed into the target.
        downstream: Tables that depend on the target.
    """

    target: str
    upstream: tuple[str, ...]
    downstream: tuple[str, ...]

    def to_prompt_string(self) -> str:
        """Format lineage for LLM prompt.

        Returns:
            Formatted string representation of lineage.
        """
        lines = [f"TARGET TABLE: {self.target}"]

        if self.upstream:
            lines.append("\nUPSTREAM DEPENDENCIES (data flows FROM these):")
            for t in self.upstream:
                lines.append(f"  - {t}")

        if self.downstream:
            lines.append("\nDOWNSTREAM DEPENDENCIES (data flows TO these):")
            for t in self.downstream:
                lines.append(f"  - {t}")

        return "\n".join(lines)


@dataclass(frozen=True)
class InvestigationContext:
    """Combined context for an investigation.

    Attributes:
        schema: Database schema from the unified datasource layer.
        lineage: Optional lineage context.
    """

    schema: SchemaResponse
    lineage: LineageContext | None = None


class ApprovalRequestType(str, Enum):
    """Types of approval requests."""

    CONTEXT_REVIEW = "context_review"
    QUERY_APPROVAL = "query_approval"
    EXECUTION_APPROVAL = "execution_approval"


class ApprovalRequest(BaseModel):
    """Request for human approval before proceeding.

    Attributes:
        investigation_id: ID of the related investigation.
        request_type: Type of approval being requested.
        context: What needs approval (e.g., schema, queries).
        requested_at: When the approval was requested.
        requested_by: System or user that requested approval.
    """

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    request_type: ApprovalRequestType
    context: dict[str, Any]
    requested_at: datetime
    requested_by: str


class ApprovalDecisionType(str, Enum):
    """Types of approval decisions."""

    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class ApprovalDecision(BaseModel):
    """Human decision on approval request.

    Attributes:
        request_id: ID of the approval request.
        decision: The decision made.
        decided_by: User who made the decision.
        decided_at: When the decision was made.
        comment: Optional comment explaining the decision.
        modifications: Optional modifications for "modified" decisions.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str
    decision: ApprovalDecisionType
    decided_by: str
    decided_at: datetime
    comment: str | None = None
    modifications: dict[str, Any] | None = None
