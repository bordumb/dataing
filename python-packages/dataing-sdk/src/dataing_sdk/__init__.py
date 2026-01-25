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
    TERMINAL_STATUSES,
    AssetRef,
    ColumnSchema,
    ConnectionTestResult,
    ContextBundle,
    Datasource,
    DatasourceSchema,
    DiffResult,
    EvidenceKind,
    ExplainResult,
    QueryResult,
    ResolvedAsset,
    Run,
    RunEvidence,
    RunStatus,
    StreamEvent,
    TableSchema,
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
    "ColumnSchema",
    "ContextBundle",
    "Datasource",
    "DatasourceSchema",
    "DiffResult",
    "EvidenceKind",
    "ExplainResult",
    "QueryResult",
    "ResolvedAsset",
    "Run",
    "RunEvidence",
    "RunStatus",
    "StreamEvent",
    "TableSchema",
    "TERMINAL_STATUSES",
    "ConnectionTestResult",
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
