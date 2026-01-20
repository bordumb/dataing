"""Core domain - Pure business logic with zero external dependencies."""

from .domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    LineageContext,
)
from .evidence import (
    Evidence as RichEvidence,
)
from .evidence import (
    EvidenceBase,
    EvidenceKind,
    HypothesisEvidence,
    HypothesisVerdict,
    LineageTraceEvidence,
    MetricCalculationEvidence,
    QueryResultEvidence,
    RunSummaryEvidence,
    SchemaSnapshotEvidence,
    create_evidence_chain,
)
from .exceptions import (
    CircuitBreakerTripped,
    DataingError,
    LLMError,
    QueryValidationError,
    SchemaDiscoveryError,
    TimeoutError,
)
from .interfaces import ContextEngine, DatabaseAdapter, LLMClient
from .state import Event, EventType, InvestigationState

__all__ = [
    # Domain types
    "AnomalyAlert",
    "Evidence",
    "Finding",
    "Hypothesis",
    "HypothesisCategory",
    "InvestigationContext",
    "LineageContext",
    # Rich evidence schema (SDK runs)
    "EvidenceKind",
    "EvidenceBase",
    "QueryResultEvidence",
    "HypothesisEvidence",
    "HypothesisVerdict",
    "LineageTraceEvidence",
    "SchemaSnapshotEvidence",
    "MetricCalculationEvidence",
    "RunSummaryEvidence",
    "RichEvidence",
    "create_evidence_chain",
    # Exceptions
    "DataingError",
    "SchemaDiscoveryError",
    "CircuitBreakerTripped",
    "QueryValidationError",
    "LLMError",
    "TimeoutError",
    # Interfaces
    "DatabaseAdapter",
    "LLMClient",
    "ContextEngine",
    # State
    "Event",
    "EventType",
    "InvestigationState",
]
