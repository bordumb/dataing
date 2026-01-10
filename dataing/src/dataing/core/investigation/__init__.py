"""Investigation domain module.

This module contains the core domain model for the investigation system,
including entities, value objects, and the step abstraction.
"""

from .entities import Branch, Investigation, InvestigationContext, Snapshot
from .values import (
    BranchStatus,
    BranchType,
    ExecutionSignal,
    StepType,
    VersionId,
)

__all__ = [
    # Entities
    "Investigation",
    "Branch",
    "Snapshot",
    "InvestigationContext",
    # Value Objects
    "VersionId",
    "BranchType",
    "BranchStatus",
    "StepType",
    "ExecutionSignal",
]
