"""Core domain - Pure business logic with zero external dependencies."""

from .domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    QueryResult,
    SchemaContext,
    TableSchema,
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
from .orchestrator import InvestigationOrchestrator, OrchestratorConfig
from .state import Event, EventType, InvestigationState

__all__ = [
    # Domain types
    "AnomalyAlert",
    "Evidence",
    "Finding",
    "Hypothesis",
    "HypothesisCategory",
    "InvestigationContext",
    "QueryResult",
    "SchemaContext",
    "TableSchema",
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
    # Orchestrator
    "InvestigationOrchestrator",
    "OrchestratorConfig",
]
