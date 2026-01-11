"""Investigation steps module.

Steps are pure functions that transform context.
The orchestrator handles persistence, locking, and flow control.
"""

from .check_patterns import CheckPatternsStep, PatternRepositoryProtocol
from .classify_intent import ClassifyIntentStep, RefinementIntent
from .execute_query import ExecuteQueryStep
from .gather_context import ContextBundle, GatherContextStep
from .generate_hypotheses import GenerateHypothesesStep
from .generate_query import GenerateQueryStep
from .interpret_evidence import InterpretEvidenceStep
from .protocol import BranchRequest, BranchSpec, Step, StepResult
from .synthesize import SynthesizeStep

__all__ = [
    "Step",
    "StepResult",
    "BranchRequest",
    "BranchSpec",
    "GatherContextStep",
    "ContextBundle",
    "CheckPatternsStep",
    "PatternRepositoryProtocol",
    "ClassifyIntentStep",
    "RefinementIntent",
    "GenerateHypothesesStep",
    "GenerateQueryStep",
    "ExecuteQueryStep",
    "InterpretEvidenceStep",
    "SynthesizeStep",
]
