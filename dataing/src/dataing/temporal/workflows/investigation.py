"""Investigation workflow definition for Temporal."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.exceptions import CancelledError

with workflow.unsafe.imports_passed_through():
    from dataing.temporal.activities import (
        check_patterns,
        counter_analyze,
        gather_context,
        generate_hypotheses,
        synthesize,
    )
    from dataing.temporal.workflows.evaluate_hypothesis import (
        EvaluateHypothesisInput,
        EvaluateHypothesisWorkflow,
    )


@dataclass
class InvestigationInput:
    """Input for starting an investigation workflow."""

    investigation_id: str
    tenant_id: str
    datasource_id: str
    alert_data: dict[str, Any]
    alert_summary: str = ""
    max_hypotheses: int = 5
    confidence_threshold: float = 0.85


@dataclass
class InvestigationResult:
    """Result of a completed investigation workflow."""

    investigation_id: str
    status: str
    context: dict[str, Any] = field(default_factory=dict)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    synthesis: dict[str, Any] = field(default_factory=dict)
    counter_analysis: dict[str, Any] | None = None
    user_feedback: dict[str, Any] | None = None


@workflow.defn
class InvestigationWorkflow:
    """Main investigation workflow that orchestrates the full investigation process.

    This workflow:
    1. Gathers context (schema, lineage, sample data)
    2. Checks for known patterns
    3. Generates hypotheses based on context and patterns
    4. Evaluates hypotheses in parallel via child workflows
    5. Synthesizes findings into root cause analysis
    6. Optionally performs counter-analysis if confidence is low

    Signals:
    - cancel_investigation: Gracefully cancel the investigation
    - user_input: Provide user feedback when AWAIT_USER is triggered
    """

    def __init__(self) -> None:
        """Initialize workflow state."""
        self._cancelled = False
        self._user_input: dict[str, Any] | None = None
        self._awaiting_user = False
        self._child_handles: list[Any] = []

    @workflow.signal
    def cancel_investigation(self) -> None:
        """Signal to cancel the investigation.

        The workflow will complete current activity and return with cancelled status.
        Child workflows will also be cancelled.
        """
        self._cancelled = True

    @workflow.signal
    def user_input(self, payload: dict[str, Any]) -> None:
        """Signal to provide user input when awaiting feedback.

        Args:
            payload: User feedback data (e.g., {"feedback": "...", "action": "..."}).
        """
        self._user_input = payload

    def _check_cancelled(self, investigation_id: str) -> InvestigationResult | None:
        """Check if cancellation was requested and return early if so.

        Args:
            investigation_id: The investigation ID for the result.

        Returns:
            InvestigationResult with cancelled status if cancelled, None otherwise.
        """
        if self._cancelled:
            return InvestigationResult(
                investigation_id=investigation_id,
                status="cancelled",
            )
        return None

    async def _cancel_children(self) -> None:
        """Cancel all running child workflows."""
        for handle in self._child_handles:
            try:
                handle.cancel()
            except Exception as e:
                workflow.logger.warning(f"Failed to cancel child workflow: {e}")

    async def _await_user_input(self, timeout_minutes: int = 60) -> dict[str, Any] | None:
        """Wait for user input signal.

        Args:
            timeout_minutes: Maximum time to wait for user input.

        Returns:
            User input payload or None if cancelled/timed out.
        """
        self._awaiting_user = True
        self._user_input = None

        try:
            # Wait for user input or cancellation
            await workflow.wait_condition(
                lambda: self._user_input is not None or self._cancelled,
                timeout=timedelta(minutes=timeout_minutes),
            )
        except TimeoutError:
            self._awaiting_user = False
            return None

        self._awaiting_user = False
        return self._user_input

    @workflow.run
    async def run(self, input: InvestigationInput) -> InvestigationResult:
        """Execute the investigation workflow.

        Args:
            input: Investigation input containing alert data and identifiers.

        Returns:
            InvestigationResult with status and findings.
        """
        alert_summary = input.alert_summary or str(input.alert_data)

        # Check cancellation before starting
        if result := self._check_cancelled(input.investigation_id):
            return result

        # Step 1: Gather context (schema, lineage, sample data)
        try:
            context = await workflow.execute_activity(
                gather_context,
                args=[input.investigation_id, input.datasource_id],
                start_to_close_timeout=timedelta(minutes=5),
            )
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
            )

        if result := self._check_cancelled(input.investigation_id):
            return result

        # Step 2: Check for known patterns (used for hypothesis hints in production)
        try:
            _patterns = await workflow.execute_activity(
                check_patterns,
                args=[input.investigation_id, input.alert_data, context],
                start_to_close_timeout=timedelta(minutes=2),
            )
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
            )

        if result := self._check_cancelled(input.investigation_id):
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
            )

        # Step 3: Generate hypotheses based on context and patterns
        try:
            hypotheses = await workflow.execute_activity(
                generate_hypotheses,
                args=[input.investigation_id, input.alert_data, context],
                start_to_close_timeout=timedelta(minutes=5),
            )
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
            )

        if result := self._check_cancelled(input.investigation_id):
            await self._cancel_children()
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
            )

        # Step 4: Evaluate hypotheses in parallel via child workflows
        evidence = await self._evaluate_hypotheses_parallel(
            investigation_id=input.investigation_id,
            hypotheses=hypotheses,
            schema_info=context.get("schema", {}),
            alert_summary=alert_summary,
            alert=input.alert_data,
        )

        if result := self._check_cancelled(input.investigation_id):
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                evidence=evidence,
            )

        # Step 5: Synthesize findings
        try:
            synthesis = await workflow.execute_activity(
                synthesize,
                args=[input.investigation_id, context, hypotheses],
                start_to_close_timeout=timedelta(minutes=5),
            )
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                evidence=evidence,
            )

        if result := self._check_cancelled(input.investigation_id):
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                evidence=evidence,
                synthesis=synthesis,
            )

        # Step 6: Counter-analysis if confidence is below threshold
        counter_analysis = None
        root_cause = synthesis.get("root_cause", {})
        confidence = root_cause.get("confidence", 1.0) if isinstance(root_cause, dict) else 1.0
        if confidence < input.confidence_threshold:
            try:
                counter_analysis = await workflow.execute_activity(
                    counter_analyze,
                    args=[input.investigation_id, synthesis, evidence],
                    start_to_close_timeout=timedelta(minutes=5),
                )
            except CancelledError:
                return InvestigationResult(
                    investigation_id=input.investigation_id,
                    status="cancelled",
                    context=context,
                    hypotheses=hypotheses,
                    evidence=evidence,
                    synthesis=synthesis,
                )

        return InvestigationResult(
            investigation_id=input.investigation_id,
            status="completed",
            context=context,
            hypotheses=hypotheses,
            evidence=evidence,
            synthesis=synthesis,
            counter_analysis=counter_analysis,
        )

    async def _evaluate_hypotheses_parallel(
        self,
        investigation_id: str,
        hypotheses: list[dict[str, Any]],
        schema_info: dict[str, Any],
        alert_summary: str,
        alert: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate hypotheses in parallel using child workflows.

        Args:
            investigation_id: ID of the investigation.
            hypotheses: List of hypothesis dictionaries.
            schema_info: Schema information for query generation.
            alert_summary: Summary of the alert being investigated.
            alert: Optional full alert data.

        Returns:
            List of evidence dictionaries from all successful evaluations.
        """
        if not hypotheses:
            return []

        # Clear previous handles
        self._child_handles = []

        # Start all child workflows
        for i, hypothesis in enumerate(hypotheses):
            # Check cancellation before starting each child
            if self._cancelled:
                await self._cancel_children()
                break

            child_input = EvaluateHypothesisInput(
                investigation_id=investigation_id,
                hypothesis_index=i,
                hypothesis=hypothesis,
                schema_info=schema_info,
                alert_summary=alert_summary,
                alert=alert,
            )
            handle = await workflow.start_child_workflow(
                EvaluateHypothesisWorkflow.run,
                child_input,
                id=f"{workflow.info().workflow_id}-hypothesis-{i}",
            )
            self._child_handles.append(handle)

        # If cancelled during child workflow creation, cancel all and return
        if self._cancelled:
            await self._cancel_children()
            return []

        # Wait for all children to complete (don't crash on individual failures)
        results = await asyncio.gather(*self._child_handles, return_exceptions=True)

        # Aggregate evidence from successful evaluations
        all_evidence: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, BaseException):
                workflow.logger.warning(f"Child workflow failed: {result}")
                continue
            # result is now narrowed to EvaluateHypothesisResult
            if result.error:
                workflow.logger.warning(
                    f"Hypothesis {result.hypothesis_id} evaluation error: {result.error}"
                )
            else:
                all_evidence.extend(result.evidence)

        return all_evidence
