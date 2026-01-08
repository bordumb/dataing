"""LLM-as-judge quality validator implementation."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel

from .assessment import QualityAssessment, ValidationResult

if TYPE_CHECKING:
    from dataing.adapters.llm.response_models import (
        InterpretationResponse,
        SynthesisResponse,
    )


JUDGE_SYSTEM_PROMPT = """You evaluate root cause analysis quality on three dimensions.

## Causal Depth (50% weight)
Evaluate the causal_chain field:
- 0.0-0.2: Empty or just restates symptom ("NULLs exist")
- 0.3-0.4: Names a cause but no mechanism ("upstream issue")
- 0.5-0.6: Cause + effect but missing intermediate steps
- 0.7-0.8: Full chain but vague on timing/mechanism
- 0.9-1.0: Complete chain with timing ("ETL timeout at 03:14 -> stale table -> JOIN NULLs")

## Specificity (30% weight)
Evaluate key_findings and supporting_evidence:
- 0.0-0.2: No concrete data
- 0.3-0.4: Vague quantities ("many rows")
- 0.5-0.6: Some numbers but no timestamps
- 0.7-0.8: Numbers + timestamps OR entity names
- 0.9-1.0: Timestamps + counts + specific table/column names

## Actionability (20% weight)
Evaluate recommendations:
- 0.0-0.2: "Investigate the issue"
- 0.3-0.4: "Check the ETL job"
- 0.5-0.6: "Check the stg_users ETL job logs"
- 0.7-0.8: "Check CloudWatch for stg_users job failures around 03:14 UTC"
- 0.9-1.0: "Run: airflow trigger_dag stg_users --conf '{\\"backfill\\": true}'"

Be calibrated: most responses score 0.4-0.7. Reserve 0.9+ for exceptional quality.

Always identify the lowest_dimension and provide a specific improvement_suggestion
(at least 20 characters) that explains how to improve that dimension."""


class LLMJudgeValidator:
    """Quality validator using LLM-as-judge with dimensional scoring.

    Attributes:
        pass_threshold: Minimum composite score to pass validation.
        judge: Pydantic AI agent configured for quality assessment.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        pass_threshold: float = 0.6,
    ) -> None:
        """Initialize the LLM judge validator.

        Args:
            api_key: Anthropic API key.
            model: Model to use for judging.
            pass_threshold: Minimum composite score to pass (0.0-1.0).
        """
        os.environ["ANTHROPIC_API_KEY"] = api_key
        self.pass_threshold = pass_threshold
        self.judge: Agent[None, QualityAssessment] = Agent(
            model=AnthropicModel(model),
            output_type=QualityAssessment,
            system_prompt=JUDGE_SYSTEM_PROMPT,
        )

    async def validate_interpretation(
        self,
        response: InterpretationResponse,
        hypothesis_title: str,
        query: str,
    ) -> ValidationResult:
        """Validate an interpretation response.

        Args:
            response: The interpretation to validate.
            hypothesis_title: Title of the hypothesis being tested.
            query: The SQL query that was executed.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        prompt = f"""Evaluate this interpretation:

HYPOTHESIS TESTED: {hypothesis_title}
QUERY RUN: {query}

RESPONSE:
- interpretation: {response.interpretation}
- causal_chain: {response.causal_chain}
- confidence: {response.confidence}
- key_findings: {response.key_findings}
- supports_hypothesis: {response.supports_hypothesis}

Score each dimension and identify what needs improvement."""

        result = await self.judge.run(prompt)

        return ValidationResult(
            passed=result.output.composite_score >= self.pass_threshold,
            assessment=result.output,
        )

    async def validate_synthesis(
        self,
        response: SynthesisResponse,
        alert_summary: str,
    ) -> ValidationResult:
        """Validate a synthesis response.

        Args:
            response: The synthesis to validate.
            alert_summary: Summary of the original anomaly alert.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        causal_chain_str = " -> ".join(response.causal_chain)

        prompt = f"""Evaluate this root cause analysis:

ORIGINAL ANOMALY: {alert_summary}

RESPONSE:
- root_cause: {response.root_cause}
- confidence: {response.confidence}
- causal_chain: {causal_chain_str}
- estimated_onset: {response.estimated_onset}
- affected_scope: {response.affected_scope}
- supporting_evidence: {response.supporting_evidence}
- recommendations: {response.recommendations}

Score each dimension and identify what needs improvement."""

        result = await self.judge.run(prompt)

        return ValidationResult(
            passed=result.output.composite_score >= self.pass_threshold,
            assessment=result.output,
        )
