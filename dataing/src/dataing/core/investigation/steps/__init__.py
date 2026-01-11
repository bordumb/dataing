"""Investigation steps module.

Steps are pure functions that transform context.
The orchestrator handles persistence, locking, and flow control.
"""

from .execute_query import ExecuteQueryStep
from .gather_context import ContextBundle, GatherContextStep
from .generate_hypotheses import GenerateHypothesesStep
from .generate_query import GenerateQueryStep
from .interpret_evidence import InterpretEvidenceStep
from .protocol import BranchRequest, BranchSpec, Step, StepResult

__all__ = [
    "Step",
    "StepResult",
    "BranchRequest",
    "BranchSpec",
    "GatherContextStep",
    "ContextBundle",
    "GenerateHypothesesStep",
    "GenerateQueryStep",
    "ExecuteQueryStep",
    "InterpretEvidenceStep",
]
