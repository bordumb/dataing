"""State management for notebook context persistence.

This module handles context persistence across cell executions
and caching using server-derived bundle_hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dataing_sdk import Context, DataingClient


@dataclass
class NotebookState:
    """Manages notebook state including context and client.

    This class persists context across cell executions and provides
    caching based on server-derived bundle_hash.

    Attributes:
        client: DataingClient instance for API calls.
        context: Current Context object (if attached).
        bundle_cache: Cache of contexts by bundle_hash.
        default_datasource_id: Default datasource for SQL parsing.
        default_platform: Default platform for URN construction.
    """

    client: DataingClient | None = None
    context: Context | None = None
    bundle_cache: dict[str, Context] = field(default_factory=dict)
    default_datasource_id: str | None = None
    default_platform: str | None = None
    _history: list[dict[str, Any]] = field(default_factory=list)

    def attach_context(self, context: Context) -> None:
        """Attach a context and cache it.

        Args:
            context: Context to attach.
        """
        self.context = context
        # Cache by bundle_hash for reuse
        self.bundle_cache[context.bundle_hash] = context
        self._history.append(
            {
                "action": "attach",
                "bundle_id": context.bundle_id,
                "bundle_hash": context.bundle_hash,
                "assets": len(context.resolved_assets),
            }
        )

    def get_cached_context(self, bundle_hash: str) -> Context | None:
        """Get a cached context by bundle_hash.

        Args:
            bundle_hash: Server-derived cache key.

        Returns:
            Cached Context or None.
        """
        return self.bundle_cache.get(bundle_hash)

    def clear_context(self) -> None:
        """Clear the current context."""
        self.context = None
        self._history.append({"action": "clear"})

    def clear_cache(self) -> None:
        """Clear the context cache."""
        self.bundle_cache.clear()
        self._history.append({"action": "clear_cache"})

    @property
    def is_attached(self) -> bool:
        """Check if a context is attached."""
        return self.context is not None

    @property
    def history(self) -> list[dict[str, Any]]:
        """Get state history for debugging."""
        return list(self._history)


# Global state instance for the notebook session
_notebook_state: NotebookState | None = None


def get_state() -> NotebookState:
    """Get the global notebook state.

    Returns:
        NotebookState instance.
    """
    global _notebook_state
    if _notebook_state is None:
        _notebook_state = NotebookState()
    return _notebook_state


def reset_state() -> None:
    """Reset the global notebook state.

    Used primarily for testing.
    """
    global _notebook_state
    _notebook_state = None
