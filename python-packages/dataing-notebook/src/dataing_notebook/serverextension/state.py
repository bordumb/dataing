"""Workspace state management for the Dataing server extension.

Implements a state machine with versioned commands to prevent drift
between magic commands, sidebar, and server extension.

State is keyed by (workspace_id, kernel_id) for multi-notebook support.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class State(str, Enum):
    """Workspace state enum."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    BOUND = "BOUND"
    RUNNING = "RUNNING"
    ERROR = "ERROR"


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_state: State, command: str, allowed_commands: list[str]) -> None:
        """Initialize the error."""
        self.current_state = current_state
        self.command = command
        self.allowed_commands = allowed_commands
        super().__init__(
            f"Invalid state transition: {command} not allowed in {current_state.value}"
        )


class StaleVersionError(Exception):
    """Raised when expected_version doesn't match current version."""

    def __init__(self, expected: int, current: int, current_state: dict[str, Any]) -> None:
        """Initialize the error."""
        self.expected = expected
        self.current = current
        self.current_state = current_state
        super().__init__(f"Stale version: expected {expected}, current {current}")


@dataclass
class ConnectionState:
    """Connection state within a workspace."""

    base_url: str | None = None
    connected: bool = False
    credential_mode: str = "none"  # keychain | env_var | session | none
    last_error: str | None = None


@dataclass
class BindingState:
    """Asset binding state within a workspace."""

    asset_urn: str | None = None
    datasource_id: str | None = None
    datasource_name: str | None = None


@dataclass
class RunState:
    """Run state within a workspace."""

    run_id: str | None = None
    status: str = "idle"  # idle | running | completed | error
    last_seq: int = 0
    started_at: str | None = None  # ISO timestamp


@dataclass
class WorkspaceState:
    """State for a single workspace-kernel pair."""

    workspace_id: str
    kernel_id: str
    state_version: int = 0
    state: State = State.DISCONNECTED

    connection: ConnectionState = field(default_factory=ConnectionState)
    binding: BindingState = field(default_factory=BindingState)
    run: RunState = field(default_factory=RunState)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "workspace_id": self.workspace_id,
            "kernel_id": self.kernel_id,
            "state_version": self.state_version,
            "state": self.state.value,
            "connection": {
                "base_url": self.connection.base_url,
                "connected": self.connection.connected,
                "credential_mode": self.connection.credential_mode,
                "last_error": self.connection.last_error,
            },
            "binding": {
                "asset_urn": self.binding.asset_urn,
                "datasource_id": self.binding.datasource_id,
                "datasource_name": self.binding.datasource_name,
            },
            "run": {
                "run_id": self.run.run_id,
                "status": self.run.status,
                "last_seq": self.run.last_seq,
                "started_at": self.run.started_at,
            },
        }


# Allowed commands per state
ALLOWED_COMMANDS: dict[State, list[str]] = {
    State.DISCONNECTED: ["connect"],
    State.CONNECTED: ["attach", "disconnect", "clear"],
    State.BOUND: ["start_run", "attach", "clear"],
    State.RUNNING: [],  # Must wait for run to complete
    State.ERROR: ["start_run", "attach", "clear"],
}


class WorkspaceManager:
    """Manages workspace states with versioned commands.

    State is keyed by (workspace_id, kernel_id) tuple.
    Implements state machine with conflict detection.
    """

    def __init__(self) -> None:
        """Initialize the workspace manager."""
        self._states: dict[tuple[str, str], WorkspaceState] = {}
        # Idempotency cache: client_request_id -> (run_id, expiry_time)
        self._request_cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl = 60.0  # 60 seconds

    def _key(self, workspace_id: str, kernel_id: str) -> tuple[str, str]:
        """Create state key from workspace and kernel IDs."""
        return (workspace_id, kernel_id)

    def get_state(self, workspace_id: str, kernel_id: str) -> WorkspaceState:
        """Get or create state for a workspace-kernel pair."""
        key = self._key(workspace_id, kernel_id)
        if key not in self._states:
            self._states[key] = WorkspaceState(workspace_id=workspace_id, kernel_id=kernel_id)
        return self._states[key]

    def _check_version(self, state: WorkspaceState, expected_version: int | None) -> None:
        """Check if expected_version matches current version."""
        if expected_version is not None and expected_version != state.state_version:
            raise StaleVersionError(
                expected=expected_version,
                current=state.state_version,
                current_state=state.to_dict(),
            )

    def _check_transition(self, state: WorkspaceState, command: str) -> None:
        """Check if command is allowed in current state."""
        allowed = ALLOWED_COMMANDS.get(state.state, [])
        if command not in allowed:
            raise StateTransitionError(
                current_state=state.state,
                command=command,
                allowed_commands=allowed,
            )

    def _increment_version(self, state: WorkspaceState) -> None:
        """Increment state version after a change."""
        state.state_version += 1

    def connect(
        self,
        workspace_id: str,
        kernel_id: str,
        base_url: str,
        credential_mode: str = "none",
        expected_version: int | None = None,
    ) -> WorkspaceState:
        """Connect to backend."""
        state = self.get_state(workspace_id, kernel_id)
        self._check_version(state, expected_version)
        self._check_transition(state, "connect")

        state.connection.base_url = base_url
        state.connection.connected = True
        state.connection.credential_mode = credential_mode
        state.connection.last_error = None
        state.state = State.CONNECTED
        self._increment_version(state)

        return state

    def disconnect(
        self,
        workspace_id: str,
        kernel_id: str,
        expected_version: int | None = None,
    ) -> WorkspaceState:
        """Disconnect from backend."""
        state = self.get_state(workspace_id, kernel_id)
        self._check_version(state, expected_version)
        self._check_transition(state, "disconnect")

        state.connection.connected = False
        state.state = State.DISCONNECTED
        self._increment_version(state)

        return state

    def attach(
        self,
        workspace_id: str,
        kernel_id: str,
        asset_urn: str,
        datasource_id: str | None = None,
        datasource_name: str | None = None,
        expected_version: int | None = None,
    ) -> WorkspaceState:
        """Attach to an asset."""
        state = self.get_state(workspace_id, kernel_id)
        self._check_version(state, expected_version)
        self._check_transition(state, "attach")

        state.binding.asset_urn = asset_urn
        state.binding.datasource_id = datasource_id
        state.binding.datasource_name = datasource_name
        state.state = State.BOUND
        self._increment_version(state)

        return state

    def set_datasource(
        self,
        workspace_id: str,
        kernel_id: str,
        datasource_id: str,
        datasource_name: str | None = None,
        expected_version: int | None = None,
    ) -> WorkspaceState:
        """Set datasource context."""
        state = self.get_state(workspace_id, kernel_id)
        self._check_version(state, expected_version)
        # Allow from CONNECTED or BOUND
        if state.state not in (State.CONNECTED, State.BOUND):
            raise StateTransitionError(
                current_state=state.state,
                command="set_datasource",
                allowed_commands=ALLOWED_COMMANDS.get(state.state, []),
            )

        state.binding.datasource_id = datasource_id
        state.binding.datasource_name = datasource_name
        self._increment_version(state)

        return state

    def _cleanup_cache(self) -> None:
        """Remove expired entries from idempotency cache."""
        now = time.time()
        expired = [k for k, (_, exp) in self._request_cache.items() if now > exp]
        for k in expired:
            del self._request_cache[k]

    def start_run(
        self,
        workspace_id: str,
        kernel_id: str,
        question: str,
        client_request_id: str,
        expected_version: int | None = None,
    ) -> tuple[WorkspaceState, str, bool]:
        """Start a new run with idempotency support.

        Returns:
            Tuple of (state, run_id, is_new).
            is_new=False means this was a duplicate request.
        """
        # Check idempotency cache first
        self._cleanup_cache()
        if client_request_id in self._request_cache:
            run_id, _ = self._request_cache[client_request_id]
            state = self.get_state(workspace_id, kernel_id)
            return (state, run_id, False)

        state = self.get_state(workspace_id, kernel_id)
        self._check_version(state, expected_version)
        self._check_transition(state, "start_run")

        # Generate run ID
        run_id = str(uuid.uuid4())
        now = time.time()

        # Update state
        state.run.run_id = run_id
        state.run.status = "running"
        state.run.last_seq = 0
        state.run.started_at = f"{now:.0f}"
        state.state = State.RUNNING
        self._increment_version(state)

        # Cache for idempotency
        self._request_cache[client_request_id] = (run_id, now + self._cache_ttl)

        return (state, run_id, True)

    def complete_run(
        self,
        workspace_id: str,
        kernel_id: str,
        success: bool = True,
    ) -> WorkspaceState:
        """Mark run as completed or failed."""
        state = self.get_state(workspace_id, kernel_id)

        # Only allowed from RUNNING
        if state.state != State.RUNNING:
            # Silently ignore if not running (may be race condition)
            return state

        state.run.status = "completed" if success else "error"
        state.state = State.ERROR if not success else State.BOUND
        self._increment_version(state)

        return state

    def update_run_progress(
        self,
        workspace_id: str,
        kernel_id: str,
        last_seq: int,
    ) -> WorkspaceState:
        """Update run progress (seq number)."""
        state = self.get_state(workspace_id, kernel_id)
        if state.state == State.RUNNING:
            state.run.last_seq = last_seq
        return state

    def clear(
        self,
        workspace_id: str,
        kernel_id: str,
        expected_version: int | None = None,
    ) -> WorkspaceState:
        """Clear binding and return to connected state."""
        state = self.get_state(workspace_id, kernel_id)
        self._check_version(state, expected_version)
        self._check_transition(state, "clear")

        state.binding = BindingState()
        state.run = RunState()
        state.state = State.CONNECTED
        self._increment_version(state)

        return state

    def delete_state(self, workspace_id: str, kernel_id: str) -> None:
        """Delete state for a workspace-kernel pair (e.g., on kernel shutdown)."""
        key = self._key(workspace_id, kernel_id)
        if key in self._states:
            del self._states[key]


# Global workspace manager instance
_workspace_manager: WorkspaceManager | None = None


def get_workspace_manager() -> WorkspaceManager:
    """Get the global workspace manager instance."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager


def reset_workspace_manager() -> None:
    """Reset the global workspace manager (for testing)."""
    global _workspace_manager
    _workspace_manager = None
