"""Temporal activity definitions for investigation steps.

This module provides:
- POC activities: Simple standalone activities for testing without dependencies
- Factory functions: Create activities with injected dependencies for production

Production Usage:
    from dataing.temporal.activities import make_gather_context_activity

    # Create activity with dependencies
    gather_context = make_gather_context_activity(context_engine, get_adapter)

    # Register with worker
    worker = Worker(client, activities=[gather_context, ...])

Testing Usage:
    from dataing.temporal.activities import gather_context, synthesize

    # Use POC activities directly (mock data)
    worker = Worker(client, activities=[gather_context, synthesize, ...])
"""

# POC activities (standalone, for testing)
# Factory functions (for production with dependency injection)
# Input/Result dataclasses
from dataing.temporal.activities.check_patterns import (
    CheckPatternsInput,
    CheckPatternsResult,
    check_patterns,
    make_check_patterns_activity,
)
from dataing.temporal.activities.counter_analyze import (
    CounterAnalyzeInput,
    CounterAnalyzeResult,
    counter_analyze,
    make_counter_analyze_activity,
)
from dataing.temporal.activities.execute_query import (
    ExecuteQueryInput,
    ExecuteQueryResult,
    execute_query,
    make_execute_query_activity,
)
from dataing.temporal.activities.gather_context import (
    GatherContextInput,
    GatherContextResult,
    gather_context,
    make_gather_context_activity,
)
from dataing.temporal.activities.generate_hypotheses import (
    GenerateHypothesesInput,
    GenerateHypothesesResult,
    generate_hypotheses,
    make_generate_hypotheses_activity,
)
from dataing.temporal.activities.generate_query import (
    GenerateQueryInput,
    GenerateQueryResult,
    generate_query,
    make_generate_query_activity,
)
from dataing.temporal.activities.interpret_evidence import (
    InterpretEvidenceInput,
    InterpretEvidenceResult,
    interpret_evidence,
    make_interpret_evidence_activity,
)
from dataing.temporal.activities.synthesize import (
    SynthesizeInput,
    SynthesizeResult,
    make_synthesize_activity,
    synthesize,
)

__all__ = [
    # POC activities
    "gather_context",
    "check_patterns",
    "generate_hypotheses",
    "generate_query",
    "execute_query",
    "interpret_evidence",
    "synthesize",
    "counter_analyze",
    # Factory functions
    "make_gather_context_activity",
    "make_check_patterns_activity",
    "make_generate_hypotheses_activity",
    "make_generate_query_activity",
    "make_execute_query_activity",
    "make_interpret_evidence_activity",
    "make_synthesize_activity",
    "make_counter_analyze_activity",
    # Input/Result types
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
]
