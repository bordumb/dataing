"""Investigation agents package.

This package contains the LLM agents used in the investigation workflow.
Agents are first-class domain concepts, not infrastructure adapters.
"""

from bond import StreamHandlers

from .client import AgentClient
from .models import (
    HypothesesResponse,
    HypothesisResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)

__all__ = [
    "AgentClient",
    "StreamHandlers",
    "HypothesesResponse",
    "HypothesisResponse",
    "InterpretationResponse",
    "QueryResponse",
    "SynthesisResponse",
]
