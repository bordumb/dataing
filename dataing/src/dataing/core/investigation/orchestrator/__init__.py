"""Investigation orchestrator module.

Provides the tick-based orchestrator for processing investigations
one step at a time with full persistence and branching support.
"""

from .base import InvestigationOrchestrator
from .types import TickResult

__all__ = [
    "InvestigationOrchestrator",
    "TickResult",
]
