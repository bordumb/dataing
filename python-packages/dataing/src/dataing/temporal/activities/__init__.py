"""Temporal activity definitions for investigation steps.

This module provides factory functions that create activities with injected
dependencies for production use.

Production Usage:
    from dataing.temporal.activities import make_gather_context_activity

    # Create activity with dependencies
    gather_context = make_gather_context_activity(context_engine, get_adapter)

    # Register with worker
    worker = Worker(client, activities=[gather_context, ...])
"""

# Factory functions (for production with dependency injection)
# Input/Result dataclasses
from dataing.temporal.activities.capture_snapshot import (
    CaptureSnapshotInput,
    CaptureSnapshotResult,
    make_capture_snapshot_activity,
)
from dataing.temporal.activities.check_patterns import (
    CheckPatternsInput,
    CheckPatternsResult,
    make_check_patterns_activity,
)
from dataing.temporal.activities.counter_analyze import (
    CounterAnalyzeInput,
    CounterAnalyzeResult,
    make_counter_analyze_activity,
)
from dataing.temporal.activities.execute_query import (
    ExecuteQueryInput,
    ExecuteQueryResult,
    make_execute_query_activity,
)
from dataing.temporal.activities.finalize_evidence import (
    FinalizeEvidenceChainInput,
    FinalizeEvidenceChainResult,
    make_finalize_evidence_chain_activity,
)
from dataing.temporal.activities.gather_context import (
    GatherContextInput,
    GatherContextResult,
    make_gather_context_activity,
)
from dataing.temporal.activities.generate_hypotheses import (
    GenerateHypothesesInput,
    GenerateHypothesesResult,
    make_generate_hypotheses_activity,
)
from dataing.temporal.activities.generate_query import (
    GenerateQueryInput,
    GenerateQueryResult,
    make_generate_query_activity,
)
from dataing.temporal.activities.interpret_evidence import (
    InterpretEvidenceInput,
    InterpretEvidenceResult,
    make_interpret_evidence_activity,
)
from dataing.temporal.activities.synthesize import (
    SynthesizeInput,
    SynthesizeResult,
    make_synthesize_activity,
)

__all__ = [
    # Factory functions
    "make_capture_snapshot_activity",
    "make_gather_context_activity",
    "make_check_patterns_activity",
    "make_generate_hypotheses_activity",
    "make_generate_query_activity",
    "make_execute_query_activity",
    "make_interpret_evidence_activity",
    "make_synthesize_activity",
    "make_counter_analyze_activity",
    "make_finalize_evidence_chain_activity",
    # Input/Result types
    "CaptureSnapshotInput",
    "CaptureSnapshotResult",
    "GatherContextInput",
    "GatherContextResult",
    "CheckPatternsInput",
    "CheckPatternsResult",
    "GenerateHypothesesInput",
    "GenerateHypothesesResult",
    "GenerateQueryInput",
    "GenerateQueryResult",
    "ExecuteQueryInput",
    "ExecuteQueryResult",
    "InterpretEvidenceInput",
    "InterpretEvidenceResult",
    "SynthesizeInput",
    "SynthesizeResult",
    "CounterAnalyzeInput",
    "CounterAnalyzeResult",
    "FinalizeEvidenceChainInput",
    "FinalizeEvidenceChainResult",
]
