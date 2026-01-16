"""Tests for branch and merge canonical ordering.

These tests verify that branch completion order is deterministic
(alphabetical by branch_id) regardless of execution order.
"""

from dataclasses import dataclass

from maistro.engine import Engine
from maistro.events import BranchCompleted, BranchStarted
from maistro.merge import DefaultMergeStrategy, LastWriteWinsMergeStrategy
from maistro.state import BranchState, RunState


@dataclass(frozen=True)
class BranchTestContext:
    """Context for branch testing."""

    value: int


class TestBranchCanonicalOrdering:
    """Tests for canonical branch ordering in merge strategies."""

    def test_default_merge_applies_branches_in_sorted_order(self) -> None:
        """DefaultMergeStrategy applies branch deltas in alphabetical order."""
        strategy = DefaultMergeStrategy()

        parent_context = {"count": 0, "source": "parent"}

        # Branches with overlapping keys - order matters
        branch_contexts = {
            "zebra": {"count": 30, "zebra_key": True},
            "alpha": {"count": 10, "alpha_key": True},
            "middle": {"count": 20, "middle_key": True},
        }

        result = strategy.merge(parent_context, branch_contexts)

        # Applied in order: alpha (count=10), middle (count=20), zebra (count=30)
        # Final count should be from zebra (last alphabetically)
        assert result["count"] == 30
        assert result["source"] == "parent"
        assert result["alpha_key"] is True
        assert result["middle_key"] is True
        assert result["zebra_key"] is True

    def test_last_write_wins_uses_alphabetically_last(self) -> None:
        """LastWriteWinsMergeStrategy uses the alphabetically last branch."""
        strategy = LastWriteWinsMergeStrategy()

        parent_context = {"count": 0}

        branch_contexts = {
            "zebra": {"count": 30},
            "alpha": {"count": 10},
        }

        result = strategy.merge(parent_context, branch_contexts)

        # Should use zebra (alphabetically last)
        assert result["count"] == 30

    def test_merge_order_is_deterministic(self) -> None:
        """Same branch contexts always produce same result regardless of dict order."""
        strategy = DefaultMergeStrategy()

        parent = {"value": 0}

        # Create the same logical set of branches in different orders
        branches1 = {"b": {"x": 2}, "a": {"x": 1}, "c": {"x": 3}}
        branches2 = {"c": {"x": 3}, "a": {"x": 1}, "b": {"x": 2}}
        branches3 = {"a": {"x": 1}, "c": {"x": 3}, "b": {"x": 2}}

        result1 = strategy.merge(parent, branches1)
        result2 = strategy.merge(parent, branches2)
        result3 = strategy.merge(parent, branches3)

        # All should produce the same result (c's value wins, alphabetically last)
        assert result1 == result2 == result3
        assert result1["x"] == 3


class TestBranchStateTracking:
    """Tests for BranchState completion tracking."""

    def test_branch_state_is_complete_when_all_expected_done(self) -> None:
        """BranchState.is_complete() returns True when all branches complete."""
        state = BranchState(
            merge_step="merge_step",
            expected=frozenset({"branch_a", "branch_b", "branch_c"}),
            completed={
                "branch_a": {"result": 1},
                "branch_b": {"result": 2},
                "branch_c": {"result": 3},
            },
        )

        assert state.is_complete()

    def test_branch_state_not_complete_when_missing(self) -> None:
        """BranchState.is_complete() returns False when branches missing."""
        state = BranchState(
            merge_step="merge_step",
            expected=frozenset({"branch_a", "branch_b", "branch_c"}),
            completed={
                "branch_a": {"result": 1},
                "branch_b": {"result": 2},
                # branch_c missing
            },
        )

        assert not state.is_complete()

    def test_branch_state_empty_expected_is_complete(self) -> None:
        """BranchState with no expected branches is immediately complete."""
        state = BranchState(
            merge_step="merge_step",
            expected=frozenset(),
            completed={},
        )

        assert state.is_complete()


class TestMergeStrategyBehavior:
    """Tests for merge strategy edge cases."""

    def test_default_merge_with_empty_branches_returns_parent(self) -> None:
        """Merge with no branch contexts returns parent context unchanged."""
        strategy = DefaultMergeStrategy()

        parent = {"count": 42, "name": "test"}
        result = strategy.merge(parent, {})

        assert result == parent

    def test_default_merge_with_single_branch(self) -> None:
        """Merge with single branch applies that branch's delta."""
        strategy = DefaultMergeStrategy()

        parent = {"count": 0, "name": "test"}
        branch_contexts = {"only_branch": {"count": 100}}

        result = strategy.merge(parent, branch_contexts)

        assert result["count"] == 100
        assert result["name"] == "test"

    def test_default_merge_non_dict_returns_branch_contexts(self) -> None:
        """For non-dict parent, DefaultMergeStrategy returns branch_contexts."""
        strategy = DefaultMergeStrategy()

        @dataclass(frozen=True)
        class CustomContext:
            value: int

        parent = CustomContext(value=10)
        branch_contexts = {"branch": {"new_value": 20}}

        result = strategy.merge(parent, branch_contexts)

        # Non-dict parent gets branch_contexts dict directly
        assert result == branch_contexts

    def test_last_write_wins_empty_branches_returns_parent(self) -> None:
        """LastWriteWins with empty branches returns parent."""
        strategy = LastWriteWinsMergeStrategy()

        parent = {"value": 42}
        result = strategy.merge(parent, {})

        assert result == parent


class TestBranchIsolation:
    """Tests for branch context isolation."""

    def test_branch_deltas_dont_modify_parent_dict(self) -> None:
        """Merging doesn't mutate the original parent context."""
        strategy = DefaultMergeStrategy()

        parent = {"count": 0, "name": "original"}
        parent_copy = dict(parent)

        branch_contexts = {"branch": {"count": 999, "new_key": "added"}}

        strategy.merge(parent, branch_contexts)

        # Original parent should be unchanged
        assert parent == parent_copy

    def test_branch_contexts_applied_independently(self) -> None:
        """Each branch's delta is applied independently from a clean parent base."""
        strategy = DefaultMergeStrategy()

        parent = {"base": 100}

        # Each branch adds its own key
        branch_contexts = {
            "alpha": {"alpha_val": 1},
            "beta": {"beta_val": 2},
            "gamma": {"gamma_val": 3},
        }

        result = strategy.merge(parent, branch_contexts)

        # All branch values should be present
        assert result["base"] == 100
        assert result["alpha_val"] == 1
        assert result["beta_val"] == 2
        assert result["gamma_val"] == 3


class TestEngineBranchEvents:
    """Tests for Engine handling of branch-related events."""

    def test_engine_handles_branch_started_event(self) -> None:
        """Engine processes BranchStarted event."""
        engine: Engine[dict[str, int]] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[dict[str, int]] = RunState(
            run_id="test_run",
            status="running",
            context={"value": 0},
            current_step="step_a",
            seq=0,
        )

        event = BranchStarted(branch_name="test_branch", start_step="step_a", seq=1)
        new_state, _ = engine.apply(state, event)

        assert new_state.seq == 1

    def test_engine_handles_branch_completed_event(self) -> None:
        """Engine processes BranchCompleted event."""
        engine: Engine[dict[str, int]] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )

        # State with pending branches
        state: RunState[dict[str, int]] = RunState(
            run_id="test_run",
            status="running",
            context={"value": 0},
            current_step="step_a",
            seq=0,
            pending_branches=BranchState(
                merge_step="step_b",
                expected=frozenset({"branch_1"}),
                completed={},
            ),
        )

        event = BranchCompleted(
            branch_name="branch_1",
            context_update={"result": 42},
            seq=1,
        )
        new_state, _ = engine.apply(state, event)

        assert new_state.seq == 1
