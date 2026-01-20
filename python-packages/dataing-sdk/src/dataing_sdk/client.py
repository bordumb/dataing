"""Dataing API client."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import AssetRef


class DataingClient:
    """Client for interacting with the Dataing API.

    This is a stub implementation. Full implementation in fn-17.2.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the Dataing client.

        Args:
            base_url: Base URL of the Dataing API.
            api_key: API key for authentication.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def run(
        self,
        assets: list[AssetRef],
        goal: str,
    ) -> None:
        """Create and start an investigation run.

        Stub implementation. Full implementation in fn-17.6.

        Args:
            assets: List of assets to investigate.
            goal: Investigation goal/question.

        Returns:
            RunHandle for streaming events.
        """
        raise NotImplementedError("Full implementation in fn-17.6")
