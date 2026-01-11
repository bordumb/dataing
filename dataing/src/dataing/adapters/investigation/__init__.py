"""Adapters for unified investigation steps.

This package provides adapters that wire the real implementations
(AgentClient, ContextEngine, BaseAdapter) to the protocol interfaces
expected by the unified investigation steps.
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
from dataing.adapters.investigation.step_factory import create_step_registry

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
    # Step factory
    "create_step_registry",
]
