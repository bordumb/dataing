"""Investigation steps module.

Steps are pure functions that transform context.
The orchestrator handles persistence, locking, and flow control.
"""

from dataing.core.investigation.pattern_extraction import PatternRepositoryProtocol

from .check_patterns import CheckPatternsStep
from .classify_intent import ClassifyIntentStep, RefinementIntent
from .counter_analyze import CounterAnalyzeStep
from .execute_query import ExecuteQueryStep
from .gather_context import ContextBundle, GatherContextStep
from .generate_hypotheses import GenerateHypothesesStep
from .generate_query import GenerateQueryStep
from .interpret_evidence import InterpretEvidenceStep
from .protocol import BranchRequest, BranchSpec, Signal, Step, StepResult
from .synthesize import SynthesizeStep

__all__ = [
    "BranchRequest",
    "BranchSpec",
    "CheckPatternsStep",
    "ClassifyIntentStep",
    "ContextBundle",
    "CounterAnalyzeStep",
    "ExecuteQueryStep",
    "GatherContextStep",
    "GenerateHypothesesStep",
    "GenerateQueryStep",
    "InterpretEvidenceStep",
    "PatternRepositoryProtocol",
    "RefinementIntent",
    "Signal",
    "Step",
    "StepResult",
    "SynthesizeStep",
]
