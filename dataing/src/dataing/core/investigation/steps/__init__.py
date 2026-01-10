"""Investigation steps module.

Steps are pure functions that transform context.
The orchestrator handles persistence, locking, and flow control.
"""

from .gather_context import ContextBundle, GatherContextStep
from .protocol import BranchRequest, BranchSpec, Step, StepResult

__all__ = [
    "Step",
    "StepResult",
    "BranchRequest",
    "BranchSpec",
    "GatherContextStep",
    "ContextBundle",
]
