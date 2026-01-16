"""Type aliases for maistro integration.

These aliases provide convenient typing for investigation steps
that use the maistro workflow engine.
"""

from __future__ import annotations

from typing import Any

from dataing.core.investigation.entities import InvestigationContext
from maistro import Step, StepResult

# Step type for investigation workflows
InvestigationStep = Step[InvestigationContext, Any, Any]

# Result type for investigation step execution
InvestigationResult = StepResult[InvestigationContext, Any]
