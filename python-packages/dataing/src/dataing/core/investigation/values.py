"""Value objects for the investigation domain.

This module contains immutable value objects and enumerations
that define the vocabulary of the investigation system.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class VersionId(BaseModel):
    """Semantic versioning for investigation snapshots.

    Format: major.minor.patch
    - major: Synthesis iterations (0 = initial, 1 = first synthesis)
    - minor: Hypothesis/evidence additions within a synthesis cycle
    - patch: Refinements/corrections that don't add new evidence
    """

    model_config = ConfigDict(frozen=True)

    major: int = 0
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        """Return version string in vX.Y.Z format."""
        return f"v{self.major}.{self.minor}.{self.patch}"

    def next_major(self) -> VersionId:
        """Return new version with incremented major, reset minor/patch."""
        return VersionId(major=self.major + 1, minor=0, patch=0)

    def next_minor(self) -> VersionId:
        """Return new version with incremented minor, reset patch."""
        return VersionId(major=self.major, minor=self.minor + 1, patch=0)

    def next_patch(self) -> VersionId:
        """Return new version with incremented patch."""
        return VersionId(major=self.major, minor=self.minor, patch=self.patch + 1)


class BranchType(str, Enum):
    """Types of investigation branches."""

    MAIN = "main"
    HYPOTHESIS = "hypothesis"
    USER = "user"
    COUNTER = "counter"
    PATTERN = "pattern"


class BranchStatus(str, Enum):
    """Branch lifecycle states."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    MERGED = "merged"
    ABANDONED = "abandoned"
    COMPLETED = "completed"


class StepType(str, Enum):
    """Atomic operations in the investigation lifecycle."""

    # Core investigation
    GATHER_CONTEXT = "gather_context"
    GENERATE_HYPOTHESES = "generate_hypotheses"
    GENERATE_QUERY = "generate_query"
    EXECUTE_QUERY = "execute_query"
    INTERPRET_EVIDENCE = "interpret_evidence"
    SYNTHESIZE = "synthesize"

    # Quality & validation
    COUNTER_ANALYZE = "counter_analyze"
    CHECK_PATTERNS = "check_patterns"

    # User interaction
    AWAIT_USER = "await_user"
    CLASSIFY_INTENT = "classify_intent"
    EXECUTE_REFINEMENT = "execute_refinement"

    # Terminal
    COMPLETE = "complete"
    FAIL = "fail"
