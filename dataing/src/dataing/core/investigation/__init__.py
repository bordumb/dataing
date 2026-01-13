"""Investigation domain module.

This module contains the core domain model for the investigation system,
including entities, value objects, and the step abstraction.

Uses maestro.Workflow for workflow execution.
"""

from maestro import Signal, Workflow

from .entities import Branch, Investigation, InvestigationContext, Snapshot
from .flow import build_investigation_workflow, run_investigation
from .pattern_extraction import (
    PatternExtractionService,
    PatternRepositoryProtocol,
)
from .registry import StepRegistry
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
    "Signal",
    # Repository
    "InvestigationRepository",
    "ExecutionLock",
    # Registry
    "StepRegistry",
    # Workflow (maestro)
    "Workflow",
    "build_investigation_workflow",
    "run_investigation",
    # Pattern Learning
    "PatternExtractionService",
    "PatternRepositoryProtocol",
]
