"""Investigation domain module.

This module contains the core domain model for the investigation system,
including entities and value objects.

Workflow execution is now handled by Temporal.
"""

from .entities import Branch, Investigation, InvestigationContext, Snapshot
from .pattern_extraction import (
    PatternExtractionService,
    PatternRepositoryProtocol,
)
from .repository import ExecutionLock, InvestigationRepository
from .values import (
    BranchStatus,
    BranchType,
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
    # Repository
    "InvestigationRepository",
    "ExecutionLock",
    # Pattern Learning
    "PatternExtractionService",
    "PatternRepositoryProtocol",
]
