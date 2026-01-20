"""Dataing SDK - Python client for the data quality investigation platform."""

from .client import DataingClient
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
    EvidenceKind,
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
    # Types
    "AssetRef",
    "ContextBundle",
    "EvidenceKind",
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
