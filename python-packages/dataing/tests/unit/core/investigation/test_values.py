"""Tests for investigation value objects."""

import pytest
from pydantic import ValidationError

from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    StepType,
    VersionId,
)


class TestVersionId:
    """Tests for VersionId value object."""

    def test_default_version(self) -> None:
        """Default version is 0.0.0."""
        v = VersionId()
        assert v.major == 0
        assert v.minor == 0
        assert v.patch == 0

    def test_str_format(self) -> None:
        """Version string format is vX.Y.Z."""
        v = VersionId(major=1, minor=2, patch=3)
        assert str(v) == "v1.2.3"

    def test_next_major(self) -> None:
        """next_major increments major and resets minor/patch."""
        v = VersionId(major=1, minor=2, patch=3)
        next_v = v.next_major()
        assert next_v.major == 2
        assert next_v.minor == 0
        assert next_v.patch == 0

    def test_next_minor(self) -> None:
        """next_minor increments minor, keeps major, resets patch."""
        v = VersionId(major=1, minor=2, patch=3)
        next_v = v.next_minor()
        assert next_v.major == 1
        assert next_v.minor == 3
        assert next_v.patch == 0

    def test_next_patch(self) -> None:
        """next_patch increments patch only."""
        v = VersionId(major=1, minor=2, patch=3)
        next_v = v.next_patch()
        assert next_v.major == 1
        assert next_v.minor == 2
        assert next_v.patch == 4

    def test_immutable(self) -> None:
        """VersionId is immutable (frozen)."""
        v = VersionId()
        with pytest.raises(ValidationError):
            v.major = 1  # type: ignore[misc]


class TestEnums:
    """Tests for enumeration types."""

    def test_branch_type_values(self) -> None:
        """BranchType has expected values."""
        assert BranchType.MAIN == "main"
        assert BranchType.HYPOTHESIS == "hypothesis"
        assert BranchType.USER == "user"
        assert BranchType.COUNTER == "counter"
        assert BranchType.PATTERN == "pattern"

    def test_branch_status_values(self) -> None:
        """BranchStatus has expected values."""
        assert BranchStatus.ACTIVE == "active"
        assert BranchStatus.SUSPENDED == "suspended"
        assert BranchStatus.MERGED == "merged"
        assert BranchStatus.ABANDONED == "abandoned"
        assert BranchStatus.COMPLETED == "completed"

    def test_step_type_values(self) -> None:
        """StepType has all expected step types."""
        # Core investigation
        assert StepType.GATHER_CONTEXT == "gather_context"
        assert StepType.GENERATE_HYPOTHESES == "generate_hypotheses"
        assert StepType.GENERATE_QUERY == "generate_query"
        assert StepType.EXECUTE_QUERY == "execute_query"
        assert StepType.INTERPRET_EVIDENCE == "interpret_evidence"
        assert StepType.SYNTHESIZE == "synthesize"
        # Quality
        assert StepType.COUNTER_ANALYZE == "counter_analyze"
        assert StepType.CHECK_PATTERNS == "check_patterns"
        # User interaction
        assert StepType.AWAIT_USER == "await_user"
        assert StepType.CLASSIFY_INTENT == "classify_intent"
        assert StepType.EXECUTE_REFINEMENT == "execute_refinement"
        # Terminal
        assert StepType.COMPLETE == "complete"
        assert StepType.FAIL == "fail"
