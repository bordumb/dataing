"""Lineage-specific exceptions."""

from __future__ import annotations


class LineageError(Exception):
    """Base exception for lineage errors."""

    pass


class DatasetNotFoundError(LineageError):
    """Dataset not found in lineage provider.

    Attributes:
        dataset_id: The dataset ID that was not found.
    """

    def __init__(self, dataset_id: str) -> None:
        """Initialize the exception.

        Args:
            dataset_id: The dataset ID that was not found.
        """
        super().__init__(f"Dataset not found: {dataset_id}")
        self.dataset_id = dataset_id


class ColumnLineageNotSupportedError(LineageError):
    """Provider doesn't support column-level lineage."""

    pass


class LineageProviderConnectionError(LineageError):
    """Failed to connect to lineage provider."""

    pass


class LineageProviderAuthError(LineageError):
    """Authentication failed for lineage provider."""

    pass


class LineageDepthExceededError(LineageError):
    """Requested lineage depth exceeds provider limits.

    Attributes:
        requested: The requested depth.
        maximum: The maximum allowed depth.
    """

    def __init__(self, requested: int, maximum: int) -> None:
        """Initialize the exception.

        Args:
            requested: The requested depth.
            maximum: The maximum allowed depth.
        """
        super().__init__(f"Requested depth {requested} exceeds maximum {maximum}")
        self.requested = requested
        self.maximum = maximum


class LineageProviderNotFoundError(LineageError):
    """Lineage provider not registered in registry.

    Attributes:
        provider: The provider type that was not found.
    """

    def __init__(self, provider: str) -> None:
        """Initialize the exception.

        Args:
            provider: The provider type that was not found.
        """
        super().__init__(f"Lineage provider not found: {provider}")
        self.provider = provider


class LineageParseError(LineageError):
    """Error parsing lineage from SQL or manifest files.

    Attributes:
        source: The source being parsed.
        detail: Details about the parse error.
    """

    def __init__(self, source: str, detail: str) -> None:
        """Initialize the exception.

        Args:
            source: The source being parsed.
            detail: Details about the parse error.
        """
        super().__init__(f"Failed to parse lineage from {source}: {detail}")
        self.source = source
        self.detail = detail
