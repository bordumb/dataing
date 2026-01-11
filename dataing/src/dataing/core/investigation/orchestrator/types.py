"""Types for investigation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from dataing.core.investigation.values import ExecutionSignal


@dataclass
class TickResult:
    """Result of a single tick execution."""

    signal: ExecutionSignal
    new_snapshot_id: UUID | None = None
    output: Any = None
    error: str | None = None
    child_branch_ids: list[UUID] | None = None
