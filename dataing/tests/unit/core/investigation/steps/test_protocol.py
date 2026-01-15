"""Tests for step protocol and StepResult."""

from dataclasses import FrozenInstanceError

import pytest
from maestro import Signal

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.protocol import BranchRequest, BranchSpec, StepResult
from dataing.core.investigation.values import (
    BranchType,
    StepType,
)


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample context."""
    return InvestigationContext(alert_summary="Test anomaly")


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_create_continue_result(self, sample_context: InvestigationContext) -> None:
        """Can create a CONTINUE result."""
        result = StepResult(
            context=sample_context,
            signal=Signal.CONTINUE,
            next_step=StepType.GENERATE_HYPOTHESES,
        )
        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.GENERATE_HYPOTHESES
        assert result.output is None
        assert result.branch_request is None

    def test_create_complete_result(self, sample_context: InvestigationContext) -> None:
        """Can create a COMPLETE result with output."""
        output = {"root_cause": "ETL failure", "confidence": 0.9}
        result = StepResult(
            context=sample_context,
            signal=Signal.COMPLETE,
            output=output,
        )
        assert result.signal == Signal.COMPLETE
        assert result.output == output
        assert result.next_step is None

    def test_create_branch_result(self, sample_context: InvestigationContext) -> None:
        """Can create a BRANCH result with branch request."""
        branch_request = BranchRequest(
            branch_type=BranchType.HYPOTHESIS,
            branches=[
                BranchSpec(name="h1", data={"hypothesis_id": "h1"}),
                BranchSpec(name="h2", data={"hypothesis_id": "h2"}),
            ],
            merge_step=StepType.SYNTHESIZE,
        )
        result = StepResult(
            context=sample_context,
            signal=Signal.BRANCH,
            branch_request=branch_request,
        )
        assert result.signal == Signal.BRANCH
        assert result.branch_request is not None
        assert len(result.branch_request.branches) == 2

    def test_result_is_frozen(self, sample_context: InvestigationContext) -> None:
        """StepResult is immutable."""
        result = StepResult(
            context=sample_context,
            signal=Signal.CONTINUE,
        )
        with pytest.raises(FrozenInstanceError):
            result.signal = Signal.FAIL


class TestBranchRequest:
    """Tests for BranchRequest."""

    def test_create_branch_request(self) -> None:
        """Can create branch request with specs."""
        request = BranchRequest(
            branch_type=BranchType.HYPOTHESIS,
            branches=[
                BranchSpec(name="h1", data={}),
            ],
            merge_step=StepType.SYNTHESIZE,
        )
        assert request.branch_type == BranchType.HYPOTHESIS
        assert request.merge_step == StepType.SYNTHESIZE
        assert request.child_start_step is None

    def test_branch_request_with_start_step(self) -> None:
        """Can specify child start step."""
        request = BranchRequest(
            branch_type=BranchType.HYPOTHESIS,
            branches=[BranchSpec(name="h1", data={})],
            merge_step=StepType.SYNTHESIZE,
            child_start_step=StepType.GENERATE_QUERY,
        )
        assert request.child_start_step == StepType.GENERATE_QUERY
