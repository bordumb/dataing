"""Anthropic Claude implementation of LLMClient."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import TYPE_CHECKING, Any, cast

import anthropic
from anthropic.types import MessageParam

from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    QueryResult,
    SchemaContext,
)
from dataing.core.exceptions import LLMError

from .prompt_manager import PromptManager

if TYPE_CHECKING:
    pass


class AnthropicClient:
    """Anthropic Claude implementation of LLMClient.

    Uses Claude for:
    - Hypothesis generation
    - Query generation with reflexion
    - Evidence interpretation
    - Finding synthesis

    Attributes:
        model: The Claude model to use.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        prompt_manager: PromptManager | None = None,
    ) -> None:
        """Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model to use (default: claude-sonnet-4-20250514).
            prompt_manager: Optional custom prompt manager.
        """
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
        self.prompt_manager = prompt_manager or PromptManager()

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate.
            context: Available schema and lineage context.
            num_hypotheses: Target number of hypotheses.

        Returns:
            List of generated hypotheses.

        Raises:
            LLMError: If LLM call fails.
        """
        messages, system = self.prompt_manager.render_messages(
            "hypothesis",
            alert=alert,
            schema_context=context.schema.to_prompt_string(),
            lineage_context=context.lineage.to_prompt_string() if context.lineage else "",
            num_hypotheses=num_hypotheses,
        )

        response = await self._call_with_retry(messages, system)
        return self._parse_hypotheses(response)

    async def generate_query(
        self,
        hypothesis: Hypothesis,
        schema: SchemaContext,
        previous_error: str | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test.
            schema: Available database schema.
            previous_error: Error from previous attempt (for reflexion).

        Returns:
            SQL query string.

        Raises:
            LLMError: If LLM call fails.
        """
        # Use reflexion template if there was a previous error
        template = "reflexion" if previous_error else "query"

        messages, system = self.prompt_manager.render_messages(
            template,
            hypothesis=hypothesis,
            schema_context=schema.to_prompt_string(),
            available_tables=[t.table_name for t in schema.tables],
            previous_error=previous_error,
            previous_query=hypothesis.suggested_query if previous_error else None,
            error_message=previous_error,
        )

        response = await self._call_with_retry(messages, system)
        return self._extract_sql(response)

    async def interpret_evidence(
        self,
        hypothesis: Hypothesis,
        query: str,
        results: QueryResult,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested.
            query: The query that was executed.
            results: The query results.

        Returns:
            Evidence with interpretation and confidence.

        Raises:
            LLMError: If LLM call fails.
        """
        messages, system = self.prompt_manager.render_messages(
            "interpretation",
            hypothesis=hypothesis,
            query=query,
            result={"row_count": results.row_count, "summary": results.to_summary()},
        )

        response = await self._call_with_retry(messages, system)
        interpretation = self._parse_interpretation(response)

        return Evidence(
            hypothesis_id=hypothesis.id,
            query=query,
            result_summary=results.to_summary(),
            row_count=results.row_count,
            supports_hypothesis=interpretation.get("supports_hypothesis"),
            confidence=interpretation.get("confidence", 0.5),
            interpretation=interpretation.get("interpretation", ""),
        )

    async def synthesize_findings(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
    ) -> Finding:
        """Synthesize all evidence into a root cause finding.

        Args:
            alert: The original anomaly alert.
            evidence: All collected evidence.

        Returns:
            Finding with root cause and recommendations.

        Raises:
            LLMError: If LLM call fails.
        """
        # Format evidence for the prompt
        evidence_data = [
            {
                "hypothesis_id": e.hypothesis_id,
                "query": e.query,
                "interpretation": e.interpretation,
                "confidence": e.confidence,
                "supports_hypothesis": e.supports_hypothesis,
            }
            for e in evidence
        ]

        messages, system = self.prompt_manager.render_messages(
            "synthesis",
            alert=alert,
            evidence=evidence_data,
        )

        response = await self._call_with_retry(messages, system)
        synthesis = self._parse_synthesis(response)

        return Finding(
            investigation_id="",  # Will be set by orchestrator
            status="completed" if synthesis.get("root_cause") else "inconclusive",
            root_cause=synthesis.get("root_cause"),
            confidence=synthesis.get("confidence", 0.0),
            evidence=evidence,
            recommendations=synthesis.get("recommendations", []),
            duration_seconds=0.0,  # Will be set by orchestrator
        )

    async def _call_with_retry(
        self,
        messages: list[dict[str, str]],
        system: str,
        max_retries: int = 3,
    ) -> str:
        """Call LLM with exponential backoff on rate limits.

        Args:
            messages: Messages to send.
            system: System prompt.
            max_retries: Maximum retry attempts.

        Returns:
            Response text.

        Raises:
            LLMError: If all retries fail.
        """
        for attempt in range(max_retries):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system,
                    messages=cast(list[MessageParam], messages),
                )
                return response.content[0].text
            except anthropic.RateLimitError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise LLMError("Rate limit exceeded after retries", retryable=True) from e
            except anthropic.APIError as e:
                raise LLMError(f"API error: {e}", retryable=True) from e
            except Exception as e:
                raise LLMError(f"LLM call failed: {e}", retryable=False) from e

        # This should not be reached, but satisfy type checker
        raise LLMError("Max retries exceeded", retryable=True)

    def _parse_hypotheses(self, response: str) -> list[Hypothesis]:
        """Parse hypothesis JSON from LLM response.

        Args:
            response: LLM response text.

        Returns:
            List of parsed Hypothesis objects.

        Raises:
            LLMError: If parsing fails.
        """
        try:
            # Extract JSON from response (may be wrapped in markdown)
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON array
                json_match = re.search(r"\[.*\]", response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise LLMError("No JSON found in response", retryable=False)

            data = json.loads(json_str)

            hypotheses = []
            for item in data:
                # Map category string to enum
                category_str = item.get("category", "data_quality")
                try:
                    category = HypothesisCategory(category_str)
                except ValueError:
                    category = HypothesisCategory.DATA_QUALITY

                hypotheses.append(
                    Hypothesis(
                        id=item.get("id", f"h{uuid.uuid4().hex[:8]}"),
                        title=item.get("title", "Unknown"),
                        category=category,
                        reasoning=item.get("reasoning", ""),
                        suggested_query=item.get("suggested_query", ""),
                    )
                )

            return hypotheses

        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse hypotheses JSON: {e}", retryable=False) from e

    def _extract_sql(self, response: str) -> str:
        """Extract SQL query from LLM response.

        Args:
            response: LLM response text.

        Returns:
            SQL query string.
        """
        # Look for SQL in code blocks
        sql_match = re.search(r"```sql\s*(.*?)\s*```", response, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()

        # Look for any code block
        code_match = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()

        # Return the whole response if no code block found
        # (LLM was asked to return only SQL)
        return response.strip()

    def _parse_interpretation(self, response: str) -> dict[str, Any]:
        """Parse interpretation JSON from LLM response.

        Args:
            response: LLM response text.

        Returns:
            Dictionary with interpretation data.
        """
        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                result: dict[str, Any] = json.loads(json_match.group(1))
                return result

            # Try raw JSON
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                return result

        except json.JSONDecodeError:
            pass

        # Default interpretation
        return {
            "supports_hypothesis": None,
            "confidence": 0.5,
            "interpretation": response,
        }

    def _parse_synthesis(self, response: str) -> dict[str, Any]:
        """Parse synthesis JSON from LLM response.

        Args:
            response: LLM response text.

        Returns:
            Dictionary with synthesis data.
        """
        try:
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                result: dict[str, Any] = json.loads(json_match.group(1))
                return result

            # Try raw JSON
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                return result

        except json.JSONDecodeError:
            pass

        # Default synthesis
        return {
            "root_cause": None,
            "confidence": 0.0,
            "recommendations": ["Unable to determine root cause"],
        }
