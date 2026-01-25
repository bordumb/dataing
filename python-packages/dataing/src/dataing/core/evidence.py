"""Evidence Schema - Rich, queryable evidence types with optional hash chain.

This module defines the evidence schema for SDK runs, providing:
1. Kind discrimination via EvidenceKind enum
2. Queryable fields for filtering across runs
3. Optional hash chain for enterprise auditability (EVIDENCE_HASH_CHAIN=true)

Evidence is normalized to enable queries like:
- "Show all runs where null_rate spike caused by schema change"
- "Find all hypothesis verdicts for table X"

Hash chain is opt-in for enterprise customers who need tamper-evidence.
Enable via EVIDENCE_HASH_CHAIN=true environment variable.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def is_hash_chain_enabled() -> bool:
    """Check if hash chain is enabled via environment variable.

    Returns:
        True if EVIDENCE_HASH_CHAIN=true, False otherwise.
    """
    return os.environ.get("EVIDENCE_HASH_CHAIN", "").lower() in ("true", "1", "yes")


class EvidenceKind(str, Enum):
    """Types of evidence that can be collected during an investigation."""

    QUERY_RESULT = "query_result"
    HYPOTHESIS = "hypothesis"
    LINEAGE_TRACE = "lineage_trace"
    SCHEMA_SNAPSHOT = "schema_snapshot"
    METRIC_CALCULATION = "metric_calculation"
    RUN_SUMMARY = "run_summary"


class EvidenceBase(BaseModel):
    """Base model for all evidence types.

    Provides common fields for identification, sequencing, and tamper-evidence.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    seq: int = Field(..., ge=1, description="Sequence number for ordering")
    kind: EvidenceKind
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prev_hash: str | None = Field(
        default=None,
        description="Hash of previous evidence in chain (None for first)",
    )
    content_hash: str = Field(
        default="",
        description="SHA256 hash of content for tamper-evidence",
    )

    def compute_content_hash(self, content: dict[str, Any]) -> str:
        """Compute SHA256 hash of content.

        Args:
            content: Dictionary content to hash.

        Returns:
            Hex-encoded SHA256 hash.
        """
        json_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()


class QueryResultEvidence(EvidenceBase):
    """Evidence from executing a SQL query."""

    kind: Literal[EvidenceKind.QUERY_RESULT] = EvidenceKind.QUERY_RESULT
    sql: str = Field(..., description="The SQL query that was executed")
    row_count: int = Field(..., ge=0, description="Number of rows returned")
    columns: list[str] = Field(default_factory=list, description="Column names")
    sample_rows: list[dict[str, Any]] = Field(
        default_factory=list, description="Sample of result rows"
    )
    execution_ms: int = Field(..., ge=0, description="Query execution time in ms")
    error: str | None = Field(default=None, description="Error message if query failed")


class HypothesisVerdict(str, Enum):
    """Possible verdicts for a hypothesis."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


class HypothesisEvidence(EvidenceBase):
    """Evidence from evaluating a hypothesis."""

    kind: Literal[EvidenceKind.HYPOTHESIS] = EvidenceKind.HYPOTHESIS
    hypothesis_id: str = Field(..., description="ID of the hypothesis evaluated")
    hypothesis_text: str = Field(..., description="The hypothesis statement")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    supporting_facts: list[str] = Field(
        default_factory=list, description="Facts supporting the hypothesis"
    )
    verdict: HypothesisVerdict = Field(..., description="Evaluation verdict")
    reasoning: str = Field(default="", description="Explanation of verdict")


class LineageTraceEvidence(EvidenceBase):
    """Evidence from lineage traversal."""

    kind: Literal[EvidenceKind.LINEAGE_TRACE] = EvidenceKind.LINEAGE_TRACE
    root_dataset: str = Field(..., description="Starting dataset for trace")
    upstream: list[str] = Field(default_factory=list, description="Upstream datasets")
    downstream: list[str] = Field(default_factory=list, description="Downstream datasets")
    edges: list[dict[str, str]] = Field(
        default_factory=list, description="Lineage edges with source/target"
    )


class SchemaSnapshotEvidence(EvidenceBase):
    """Evidence capturing schema at a point in time."""

    kind: Literal[EvidenceKind.SCHEMA_SNAPSHOT] = EvidenceKind.SCHEMA_SNAPSHOT
    dataset: str = Field(..., description="Dataset name")
    columns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Column definitions with name, type, nullable",
    )
    row_count: int | None = Field(default=None, description="Approximate row count")
    last_modified: datetime | None = Field(default=None, description="Last modification time")


class MetricCalculationEvidence(EvidenceBase):
    """Evidence from calculating a metric value."""

    kind: Literal[EvidenceKind.METRIC_CALCULATION] = EvidenceKind.METRIC_CALCULATION
    metric_name: str = Field(..., description="Name of the metric")
    metric_type: str = Field(..., description="Type of metric (count, rate, etc.)")
    value: float = Field(..., description="Calculated metric value")
    expected_value: float | None = Field(default=None, description="Expected/baseline value")
    deviation_pct: float | None = Field(
        default=None, description="Percentage deviation from expected"
    )
    dimensions: dict[str, str] = Field(
        default_factory=dict, description="Dimension values for this calculation"
    )


class RunSummaryEvidence(EvidenceBase):
    """Evidence summarizing the entire run."""

    kind: Literal[EvidenceKind.RUN_SUMMARY] = EvidenceKind.RUN_SUMMARY
    root_cause: str | None = Field(default=None, description="Identified root cause")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence in finding")
    recommendations: list[str] = Field(default_factory=list, description="Recommended actions")
    hypotheses_evaluated: int = Field(default=0, description="Number of hypotheses evaluated")
    queries_executed: int = Field(default=0, description="Number of queries executed")
    duration_seconds: float = Field(default=0.0, description="Total run duration")


# Discriminated union type for all evidence
Evidence = Annotated[
    QueryResultEvidence
    | HypothesisEvidence
    | LineageTraceEvidence
    | SchemaSnapshotEvidence
    | MetricCalculationEvidence
    | RunSummaryEvidence,
    Field(discriminator="kind"),
]


def create_evidence_chain(
    run_id: UUID,
    kind: EvidenceKind,
    content: dict[str, Any],
    prev_hash: str | None = None,
    seq: int = 1,
) -> EvidenceBase:
    """Create an evidence item with optional hash chain.

    Args:
        run_id: Run UUID.
        kind: Evidence kind.
        content: Evidence content dict.
        prev_hash: Hash of previous evidence in chain (only used if hash chain enabled).
        seq: Sequence number.

    Returns:
        Evidence instance with computed content_hash.

    Note:
        Hash chain is only enabled when EVIDENCE_HASH_CHAIN=true.
        When disabled, prev_hash is always None.
    """
    # Only include prev_hash if hash chain is enabled
    effective_prev_hash = prev_hash if is_hash_chain_enabled() else None

    # Create base evidence to compute hash
    base = EvidenceBase(
        run_id=run_id,
        seq=seq,
        kind=kind,
        prev_hash=effective_prev_hash,
    )
    content_hash = base.compute_content_hash(content)

    # Map kind to concrete type
    evidence_classes = {
        EvidenceKind.QUERY_RESULT: QueryResultEvidence,
        EvidenceKind.HYPOTHESIS: HypothesisEvidence,
        EvidenceKind.LINEAGE_TRACE: LineageTraceEvidence,
        EvidenceKind.SCHEMA_SNAPSHOT: SchemaSnapshotEvidence,
        EvidenceKind.METRIC_CALCULATION: MetricCalculationEvidence,
        EvidenceKind.RUN_SUMMARY: RunSummaryEvidence,
    }

    cls = evidence_classes.get(kind, EvidenceBase)
    result: EvidenceBase = cls(
        run_id=run_id,
        seq=seq,
        kind=kind,
        prev_hash=effective_prev_hash,
        content_hash=content_hash,
        **content,
    )
    return result
