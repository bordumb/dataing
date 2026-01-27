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

Hash computation uses RFC 8785 (JSON Canonicalization Scheme) for deterministic
serialization, with a domain-separated SHA-256 hash covering chain metadata
(seq, kind, prev_hash) in addition to content.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

import rfc8785
from pydantic import BaseModel, ConfigDict, Field

# Domain separation prefix for evidence hash computation.
# Prevents second preimage attacks by distinguishing evidence hashes
# from other SHA-256 hashes in the system.
_HASH_DOMAIN_PREFIX = b"evidence_v1:"


def is_hash_chain_enabled() -> bool:
    """Check if hash chain is enabled via environment variable.

    Returns:
        True if EVIDENCE_HASH_CHAIN=true, False otherwise.
    """
    return os.environ.get("EVIDENCE_HASH_CHAIN", "").lower() in ("true", "1", "yes")


def compute_content_hash(
    seq: int,
    kind: str,
    prev_hash: str | None,
    content: dict[str, Any],
) -> str:
    """Compute SHA-256 hash of evidence with chain metadata.

    Uses RFC 8785 canonical JSON serialization for deterministic output
    across Python versions and platforms. Includes chain metadata (seq, kind,
    prev_hash) in the hash to authenticate ordering and linkage.

    Args:
        seq: Evidence sequence number.
        kind: Evidence kind discriminator.
        prev_hash: Hash of previous evidence in chain (None for first item).
        content: Evidence content dict (must be JSON-safe).

    Returns:
        64-character hex-encoded SHA-256 hash.
    """
    hashable: dict[str, Any] = {
        "seq": seq,
        "kind": kind,
        "prev_hash": prev_hash,
        "content": content,
    }
    canonical_bytes = rfc8785.dumps(hashable)
    return hashlib.sha256(_HASH_DOMAIN_PREFIX + canonical_bytes).hexdigest()


def verify_chain(
    evidence_items: list[dict[str, Any]],
) -> tuple[bool, int | None, str | None]:
    """Verify integrity of an evidence hash chain.

    Pure function that validates:
    1. Each item's content_hash matches recomputed hash
    2. Each item's prev_hash matches the previous item's content_hash
    3. First item has prev_hash = None

    Uses timing-safe comparison via hmac.compare_digest().

    Args:
        evidence_items: Evidence dicts ordered by seq. Each must contain
            keys: seq, kind, prev_hash, content_hash, content.

    Returns:
        Tuple of (is_valid, first_broken_seq, error_message).
        If valid, returns (True, None, None).
        If broken, returns (False, broken_seq, description).
    """
    if not evidence_items:
        return True, None, None

    for i, item in enumerate(evidence_items):
        seq = item.get("seq", i + 1)
        kind = item.get("kind", "")
        prev_hash = item.get("prev_hash")
        content_hash = item.get("content_hash", "")
        content = item.get("content", {})

        # Verify genesis block
        if i == 0 and prev_hash is not None:
            return (
                False,
                seq,
                f"Genesis item (seq={seq}) must have prev_hash=None, " f"got '{prev_hash}'",
            )

        # Verify prev_hash linkage
        if i > 0:
            expected_prev = evidence_items[i - 1].get("content_hash", "")
            if not hmac.compare_digest(
                str(prev_hash or ""),
                str(expected_prev),
            ):
                return (
                    False,
                    seq,
                    f"Item seq={seq} prev_hash mismatch: "
                    f"expected '{expected_prev}', got '{prev_hash}'",
                )

        # Verify content_hash
        expected_hash = compute_content_hash(
            seq=seq,
            kind=kind,
            prev_hash=prev_hash,
            content=content,
        )
        if not hmac.compare_digest(content_hash, expected_hash):
            return (
                False,
                seq,
                f"Item seq={seq} content_hash mismatch: "
                f"expected '{expected_hash}', got '{content_hash}'",
            )

    return True, None, None


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
    timestamp: datetime | None = None,
) -> EvidenceBase:
    """Create an evidence item with optional hash chain.

    Args:
        run_id: Run UUID.
        kind: Evidence kind.
        content: Evidence content dict.
        prev_hash: Hash of previous evidence in chain (only used if hash chain enabled).
        seq: Sequence number.
        timestamp: Explicit timestamp (defaults to now UTC).

    Returns:
        Evidence instance with computed content_hash.

    Note:
        Hash chain is only enabled when EVIDENCE_HASH_CHAIN=true.
        When disabled, prev_hash is always None.
    """
    # Only include prev_hash if hash chain is enabled
    effective_prev_hash = prev_hash if is_hash_chain_enabled() else None

    # Compute hash using module-level function (no throwaway instance)
    content_hash = compute_content_hash(
        seq=seq,
        kind=kind.value,
        prev_hash=effective_prev_hash,
        content=content,
    )

    # Use explicit timestamp to avoid mismatch between hash and stored value
    ts = timestamp or datetime.now(UTC)

    # Map kind to concrete type
    evidence_classes: dict[EvidenceKind, type[EvidenceBase]] = {
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
        timestamp=ts,
        prev_hash=effective_prev_hash,
        content_hash=content_hash,
        **content,
    )
    return result
