"""Dataing SDK - Python client for the data quality investigation platform."""

from .client import DataingClient
from .context import Context, from_sql
from .exceptions import (
    AmbiguousAssetError,
    AuthError,
    DataingError,
    NotFoundError,
    RateLimitError,
    ReplayWindowExpiredError,
    ServerError,
    StreamError,
    TimeoutError,
    ValidationError,
)
from .types import (
    AssetRef,
    ContextBundle,
    DiffResult,
    EvidenceKind,
    ExplainResult,
    QueryResult,
    ResolvedAsset,
    Run,
    RunEvidence,
    RunStatus,
    StreamEvent,
    TERMINAL_STATUSES,
)

__version__ = "0.1.0"

__all__ = [
    # Client
    "DataingClient",
    # Context
    "Context",
    "from_sql",
    # Types
    "AssetRef",
    "ContextBundle",
    "DiffResult",
    "EvidenceKind",
    "ExplainResult",
    "QueryResult",
    "ResolvedAsset",
    "Run",
    "RunEvidence",
    "RunStatus",
    "StreamEvent",
    "TERMINAL_STATUSES",
    # Exceptions
    "DataingError",
    "AuthError",
    "RateLimitError",
    "AmbiguousAssetError",
    "NotFoundError",
    "ValidationError",
    "ServerError",
    "TimeoutError",
    "StreamError",
    "ReplayWindowExpiredError",
]
