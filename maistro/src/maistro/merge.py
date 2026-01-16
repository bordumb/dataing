"""Merge strategy protocol and implementations.

Merge strategies define how to combine results from parallel branches back
into the parent context. All strategies are stateless - pure functions wrapped
in classes to satisfy the Protocol interface.

The new design uses dict[str, Any] for branch contexts, where keys are branch
names and values are the context_update deltas from each branch.
"""

from __future__ import annotations

from typing import Any, Protocol


class MergeStrategy(Protocol):
    """Protocol for merging branch contexts.

    Implementations define how to combine results from multiple child branches
    back into a parent context. Strategies must be stateless - all information
    comes from the method parameters.

    """

    def merge(
        self,
        parent_context: Any,
        branch_contexts: dict[str, Any],
    ) -> Any:
        """Merge branch contexts into parent.

        Args:
            parent_context: The context from before branching.
            branch_contexts: Map of branch_name -> context_update delta.

        Returns:
            Merged context to continue with.

        """
        ...


class DefaultMergeStrategy:
    """Default merge strategy that combines all branch deltas.

    If the parent context is a dict, branch context deltas are merged into it.
    Otherwise, returns the branch_contexts dict directly.

    """

    def merge(
        self,
        parent_context: Any,
        branch_contexts: dict[str, Any],
    ) -> Any:
        """Merge branch contexts into parent.

        For dict parent contexts, iterates through branches in sorted order
        and applies each branch's context_update delta. Non-dict parent
        contexts receive the branch_contexts dict directly.

        Args:
            parent_context: The context from before branching.
            branch_contexts: Map of branch_name -> context_update delta.

        Returns:
            Merged context to continue with.

        """
        if isinstance(parent_context, dict):
            result = dict(parent_context)
            # Apply branch deltas in sorted order for determinism
            for branch_name in sorted(branch_contexts.keys()):
                branch_delta = branch_contexts[branch_name]
                if isinstance(branch_delta, dict):
                    result.update(branch_delta)
            return result
        return branch_contexts


class LastWriteWinsMergeStrategy:
    """Merge strategy that uses the last branch context (alphabetically).

    Useful when only one branch's result should be used, and you want
    deterministic behavior based on branch names.

    """

    def merge(
        self,
        parent_context: Any,
        branch_contexts: dict[str, Any],
    ) -> Any:
        """Use the context from the last branch (alphabetically by name).

        Args:
            parent_context: The context from before branching.
            branch_contexts: Map of branch_name -> context_update delta.

        Returns:
            The context_update from the alphabetically last branch.

        """
        if not branch_contexts:
            return parent_context

        last_branch = sorted(branch_contexts.keys())[-1]
        last_delta = branch_contexts[last_branch]

        if isinstance(parent_context, dict) and isinstance(last_delta, dict):
            result = dict(parent_context)
            result.update(last_delta)
            return result

        return last_delta
