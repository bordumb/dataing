"""Adapters for investigation components.

This package provides adapters that wire the real implementations
(AgentClient, ContextEngine, BaseAdapter) to the protocol interfaces
expected by investigation activities.
"""

from dataing.adapters.investigation.context_adapter import (
    ContextEngineAdapter,
    GatheredContextWrapper,
    LineageWrapper,
    SchemaWrapper,
)
from dataing.adapters.investigation.database_adapter import DatabaseAdapter
from dataing.adapters.investigation.llm_adapter import (
    HypothesisLLMAdapter,
    InterpretEvidenceLLMAdapter,
    QueryLLMAdapter,
    SynthesisLLMAdapter,
)
from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository

__all__ = [
    # Context adapters
    "ContextEngineAdapter",
    "GatheredContextWrapper",
    "LineageWrapper",
    "SchemaWrapper",
    # Database adapters
    "DatabaseAdapter",
    # LLM adapters
    "HypothesisLLMAdapter",
    "InterpretEvidenceLLMAdapter",
    "QueryLLMAdapter",
    "SynthesisLLMAdapter",
    # Pattern adapters
    "InMemoryPatternRepository",
]
