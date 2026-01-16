"""Type aliases for maestro integration.

These aliases provide convenient typing for investigation steps
that use the maestro workflow engine.
"""

from __future__ import annotations

from typing import Any

from dataing.core.investigation.entities import InvestigationContext
from maestro import Step, StepResult

# Step type for investigation workflows
InvestigationStep = Step[InvestigationContext, Any, Any]

# Result type for investigation step execution
InvestigationResult = StepResult[InvestigationContext, Any]
