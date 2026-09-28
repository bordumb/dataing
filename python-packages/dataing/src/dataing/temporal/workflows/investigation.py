"""Investigation workflow definition for Temporal."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError, ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from dataing.temporal.activities import (
        CaptureSnapshotInput,
        CheckPatternsInput,
        CounterAnalyzeInput,
        FinalizeEvidenceChainInput,
        GatherContextInput,
        GenerateHypothesesInput,
        SynthesizeInput,
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
    enable_snapshots: bool = True  # Enable snapshot capture for hydration


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
    root_hash: str | None = None
    snapshot_paths: list[str] = field(default_factory=list)  # Paths to captured snapshots


@dataclass
class InvestigationQueryStatus:
    """Status returned by the get_status query."""

    investigation_id: str
    current_step: str
    progress: float  # 0.0 to 1.0
    is_complete: bool
    is_cancelled: bool
    is_awaiting_user: bool
    hypotheses_count: int
    hypotheses_evaluated: int
    evidence_count: int


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
        # Progress tracking
        self._investigation_id = ""
        self._tenant_id = ""
        self._current_step = "initializing"
        self._progress = 0.0
        self._is_complete = False
        self._hypotheses_count = 0
        self._hypotheses_evaluated = 0
        self._evidence_count = 0
        # Snapshot tracking
        self._enable_snapshots = True
        self._snapshot_paths: list[str] = []

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

    @workflow.query
    def get_status(self) -> InvestigationQueryStatus:
        """Query the current status of the investigation.

        Returns:
            InvestigationQueryStatus with current progress and state.
        """
        return InvestigationQueryStatus(
            investigation_id=self._investigation_id,
            current_step=self._current_step,
            progress=self._progress,
            is_complete=self._is_complete,
            is_cancelled=self._cancelled,
            is_awaiting_user=self._awaiting_user,
            hypotheses_count=self._hypotheses_count,
            hypotheses_evaluated=self._hypotheses_evaluated,
            evidence_count=self._evidence_count,
        )

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
                snapshot_paths=self._snapshot_paths,
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

    async def _capture_snapshot(
        self,
        checkpoint: str,
        alert: dict[str, Any] | None = None,
        hypotheses: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        synthesis: dict[str, Any] | None = None,
        schema_snapshot: dict[str, Any] | None = None,
        lineage_snapshot: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Capture investigation snapshot asynchronously (fire-and-forget).

        Snapshot capture is non-blocking: failures are logged but don't
        interrupt the investigation workflow.

        Args:
            checkpoint: The checkpoint name (start, hypothesis_generated, etc).
            alert: Alert data that triggered the investigation.
            hypotheses: Generated hypotheses.
            evidence: Collected evidence.
            synthesis: Synthesis results.
            schema_snapshot: Schema context.
            lineage_snapshot: Lineage context.
            metadata: Additional metadata.
        """
        if not self._enable_snapshots:
            return

        try:
            snapshot_input = CaptureSnapshotInput(
                investigation_id=self._investigation_id,
                tenant_id=self._tenant_id,
                checkpoint=checkpoint,
                alert=alert,
                hypotheses=hypotheses,
                evidence=evidence,
                synthesis=synthesis,
                schema_snapshot=schema_snapshot,
                lineage_snapshot=lineage_snapshot,
                metadata=metadata,
            )
            # Execute with short timeout - snapshot capture shouldn't block
            result = await workflow.execute_activity(
                "capture_snapshot",
                snapshot_input,
                start_to_close_timeout=timedelta(minutes=2),
            )
            if result.get("success") and result.get("storage_path"):
                self._snapshot_paths.append(result["storage_path"])
            elif result.get("error"):
                workflow.logger.warning(f"Snapshot capture warning: {result['error']}")
        except Exception as e:
            # Non-fatal: snapshot capture should never block investigation
            workflow.logger.warning(f"Snapshot capture failed (non-fatal): {e}")

    @workflow.run
    async def run(self, input: InvestigationInput) -> InvestigationResult:
        """Execute the investigation workflow.

        Args:
            input: Investigation input containing alert data and identifiers.

        Returns:
            InvestigationResult with status and findings.
        """
        # Initialize progress tracking
        self._investigation_id = input.investigation_id
        self._tenant_id = input.tenant_id
        self._current_step = "starting"
        self._progress = 0.0
        self._enable_snapshots = input.enable_snapshots
        self._snapshot_paths = []

        alert_summary = input.alert_summary or str(input.alert_data)

        # Check cancellation before starting
        if result := self._check_cancelled(input.investigation_id):
            return result

        # Step 1: Gather context (schema, lineage, sample data)
        self._current_step = "gather_context"
        self._progress = 0.1
        try:
            gather_input = GatherContextInput(
                investigation_id=input.investigation_id,
                tenant_id=input.tenant_id,
                datasource_id=input.datasource_id,
                alert=input.alert_data,
            )
            gather_result = await workflow.execute_activity(
                "gather_context",
                gather_input,
                start_to_close_timeout=timedelta(minutes=5),
            )
            # Result is returned as dict from Temporal serialization
            context = {
                "schema": gather_result.get("schema_info", {}),
                "lineage": gather_result.get("lineage_info"),
            }
            if gather_result.get("error"):
                workflow.logger.warning(f"Context gathering warning: {gather_result['error']}")
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                snapshot_paths=self._snapshot_paths,
            )
        self._progress = 0.2

        # Capture START snapshot after context gathered
        await self._capture_snapshot(
            checkpoint="start",
            alert=input.alert_data,
            schema_snapshot=context.get("schema"),
            lineage_snapshot=context.get("lineage"),
        )

        if result := self._check_cancelled(input.investigation_id):
            return result

        # Step 2: Check for known patterns (used for hypothesis hints in production)
        self._current_step = "check_patterns"
        try:
            patterns_input = CheckPatternsInput(
                investigation_id=input.investigation_id,
                alert_summary=alert_summary,
            )
            _patterns_result = await workflow.execute_activity(
                "check_patterns",
                patterns_input,
                start_to_close_timeout=timedelta(minutes=2),
            )
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                snapshot_paths=self._snapshot_paths,
            )
        self._progress = 0.3

        if result := self._check_cancelled(input.investigation_id):
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                snapshot_paths=self._snapshot_paths,
            )

        # Step 3: Generate hypotheses based on context and patterns
        self._current_step = "generate_hypotheses"
        try:
            # Get matched patterns from the check_patterns result
            if _patterns_result:
                matched_patterns = _patterns_result.get("matched_patterns", [])
            else:
                matched_patterns = []
            hypotheses_input = GenerateHypothesesInput(
                investigation_id=input.investigation_id,
                alert_summary=alert_summary,
                alert=input.alert_data,
                schema_info=context.get("schema"),
                lineage_info=context.get("lineage"),
                matched_patterns=matched_patterns,
                max_hypotheses=input.max_hypotheses,
            )
            hypotheses_result = await workflow.execute_activity(
                "generate_hypotheses",
                hypotheses_input,
                start_to_close_timeout=timedelta(minutes=5),
            )
            hypotheses = hypotheses_result.get("hypotheses", [])
            if hypotheses_result.get("error"):
                err = hypotheses_result["error"]
                workflow.logger.warning(f"Hypothesis generation warning: {err}")
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                snapshot_paths=self._snapshot_paths,
            )
        self._hypotheses_count = len(hypotheses) if hypotheses else 0
        self._progress = 0.4

        # Capture HYPOTHESIS_GENERATED snapshot
        await self._capture_snapshot(
            checkpoint="hypothesis_generated",
            alert=input.alert_data,
            hypotheses=hypotheses,
            schema_snapshot=context.get("schema"),
            lineage_snapshot=context.get("lineage"),
        )

        if result := self._check_cancelled(input.investigation_id):
            await self._cancel_children()
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                snapshot_paths=self._snapshot_paths,
            )

        # Step 4: Evaluate hypotheses in parallel via child workflows
        self._current_step = "evaluate_hypotheses"
        evidence, untested_hypotheses = await self._evaluate_hypotheses_parallel(
            investigation_id=input.investigation_id,
            hypotheses=hypotheses,
            schema_info=context.get("schema", {}),
            alert_summary=alert_summary,
            tenant_id=input.tenant_id,
            datasource_id=input.datasource_id,
            alert=input.alert_data,
        )
        self._evidence_count = len(evidence) if evidence else 0
        self._progress = 0.7

        if result := self._check_cancelled(input.investigation_id):
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                evidence=evidence,
                snapshot_paths=self._snapshot_paths,
            )

        # Step 5: Synthesize findings
        self._current_step = "synthesize"
        try:
            synthesize_input = SynthesizeInput(
                investigation_id=input.investigation_id,
                evidence=evidence,
                hypotheses=hypotheses,
                alert_summary=alert_summary,
                confidence_threshold=input.confidence_threshold,
                untested_hypotheses=untested_hypotheses,
            )
            synthesize_result = await workflow.execute_activity(
                "synthesize",
                synthesize_input,
                start_to_close_timeout=timedelta(minutes=5),
            )
            # Build synthesis dict from result fields
            synthesis = {
                "root_cause": synthesize_result.get("root_cause", ""),
                "confidence": synthesize_result.get("confidence", 0.0),
                "recommendations": synthesize_result.get("recommendations", []),
                "supporting_evidence": synthesize_result.get("supporting_evidence", []),
            }
            if synthesize_result.get("error"):
                workflow.logger.warning(f"Synthesis warning: {synthesize_result['error']}")
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                evidence=evidence,
                snapshot_paths=self._snapshot_paths,
            )
        self._progress = 0.85

        if result := self._check_cancelled(input.investigation_id):
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                evidence=evidence,
                synthesis=synthesis,
                snapshot_paths=self._snapshot_paths,
            )

        # Step 5b: Finalize evidence chain (build hash chain and persist)
        root_hash: str | None = None
        try:
            finalize_input = FinalizeEvidenceChainInput(
                investigation_id=input.investigation_id,
                evidence=evidence,
                hypotheses=hypotheses,
                synthesis=synthesis,
            )
            finalize_result = await workflow.execute_activity(
                "finalize_evidence_chain",
                finalize_input,
                start_to_close_timeout=timedelta(minutes=2),
            )
            root_hash = finalize_result.get("root_hash")
            if finalize_result.get("error"):
                workflow.logger.warning(
                    f"Evidence chain finalization warning: {finalize_result['error']}"
                )
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                hypotheses=hypotheses,
                evidence=evidence,
                synthesis=synthesis,
                snapshot_paths=self._snapshot_paths,
            )
        except Exception as e:
            # Non-fatal: investigation can complete without evidence chain
            workflow.logger.warning(f"Evidence chain finalization failed: {e}")

        # Step 6: Counter-analysis if confidence is below threshold
        counter_analysis = None
        confidence = synthesis.get("confidence", 1.0)
        needs_counter = synthesize_result.get("needs_counter_analysis", False)
        if needs_counter or confidence < input.confidence_threshold:
            self._current_step = "counter_analyze"
            try:
                counter_input = CounterAnalyzeInput(
                    investigation_id=input.investigation_id,
                    synthesis=synthesis,
                    evidence=evidence,
                    hypotheses=hypotheses,
                )
                counter_result = await workflow.execute_activity(
                    "counter_analyze",
                    counter_input,
                    start_to_close_timeout=timedelta(minutes=5),
                )
                # Build counter_analysis dict from result fields
                counter_analysis = {
                    "alternative_explanations": counter_result.get("alternative_explanations", []),
                    "weaknesses": counter_result.get("weaknesses", []),
                    "confidence_adjustment": counter_result.get("confidence_adjustment", 0.0),
                    "recommendation": counter_result.get("recommendation", "accept"),
                }
                if counter_result.get("error"):
                    workflow.logger.warning(f"Counter-analysis warning: {counter_result['error']}")
            except CancelledError:
                return InvestigationResult(
                    investigation_id=input.investigation_id,
                    status="cancelled",
                    context=context,
                    hypotheses=hypotheses,
                    evidence=evidence,
                    synthesis=synthesis,
                    snapshot_paths=self._snapshot_paths,
                )

        # Publish the outcome for the app and, for runs started from an issue, its thread
        if workflow.patched("outcome-v1"):
            await self._publish_outcome(
                input=input,
                hypotheses=hypotheses,
                evidence=evidence,
                untested=untested_hypotheses,
                synthesis=synthesis,
                counter_analysis=counter_analysis,
            )

        # Capture COMPLETE snapshot
        await self._capture_snapshot(
            checkpoint="complete",
            alert=input.alert_data,
            hypotheses=hypotheses,
            evidence=evidence,
            synthesis=synthesis,
            schema_snapshot=context.get("schema"),
            lineage_snapshot=context.get("lineage"),
            metadata={"counter_analysis": counter_analysis, "root_hash": root_hash},
        )

        # Mark complete
        self._current_step = "completed"
        self._progress = 1.0
        self._is_complete = True

        return InvestigationResult(
            investigation_id=input.investigation_id,
            status="completed",
            context=context,
            hypotheses=hypotheses,
            evidence=evidence,
            synthesis=synthesis,
            counter_analysis=counter_analysis,
            root_hash=root_hash,
            snapshot_paths=self._snapshot_paths,
        )

    async def _publish_outcome(
        self,
        *,
        input: InvestigationInput,
        hypotheses: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        untested: list[dict[str, Any]],
        synthesis: dict[str, Any],
        counter_analysis: dict[str, Any] | None,
    ) -> None:
        """Write the outcome (investigation row, linked run, issue thread). Non-fatal."""
        payload = {
            "investigation_id": input.investigation_id,
            "tenant_id": input.tenant_id,
            "issue_id": (input.alert_data or {}).get("issue_id"),
            "synthesis": synthesis,
            "hypotheses": hypothesis_statuses(hypotheses, evidence, untested),
            "counter_analysis": counter_analysis,
        }
        try:
            await workflow.execute_activity(
                "publish_investigation_outcome",
                payload,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
        except Exception as e:
            workflow.logger.warning(f"Publishing the outcome failed (non-fatal): {e}")

    async def _evaluate_hypotheses_parallel(
        self,
        investigation_id: str,
        hypotheses: list[dict[str, Any]],
        schema_info: dict[str, Any],
        alert_summary: str,
        tenant_id: str,
        datasource_id: str,
        alert: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Evaluate hypotheses in parallel using child workflows.

        Args:
            investigation_id: ID of the investigation.
            hypotheses: List of hypothesis dictionaries.
            schema_info: Schema information for query generation.
            alert_summary: Summary of the alert being investigated.
            tenant_id: ID of the tenant that owns the investigation and datasource.
            datasource_id: ID of the datasource to query.
            alert: Optional full alert data.

        Returns:
            Tuple of (evidence from successful evaluations, untested hypotheses).
            A hypothesis is untested when its evaluation failed; synthesis must not
            read that as the hypothesis being refuted.
        """
        if not hypotheses:
            return [], []

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
                tenant_id=tenant_id,
                datasource_id=datasource_id,
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
            return [], []

        # Wait for all children to complete (don't crash on individual failures)
        results = await asyncio.gather(*self._child_handles, return_exceptions=True)

        # Aggregate evidence; a failed evaluation leaves its hypothesis untested
        all_evidence: list[dict[str, Any]] = []
        untested: list[dict[str, Any]] = []
        evaluated_count = 0
        for i, (hypothesis, result) in enumerate(zip(hypotheses, results, strict=True)):
            if isinstance(result, BaseException):
                reason = _describe_failure(result)
                workflow.logger.warning(f"Child workflow failed: {reason}")
                untested.append(_untested(hypothesis, i, f"Evaluation failed: {reason}"))
                continue
            # result is now narrowed to EvaluateHypothesisResult
            evaluated_count += 1
            self._hypotheses_evaluated = evaluated_count
            if result.error:
                workflow.logger.warning(
                    f"Hypothesis {result.hypothesis_id} evaluation error: {result.error}"
                )
                untested.append(_untested(hypothesis, i, result.error))
            else:
                all_evidence.extend(result.evidence)

        return all_evidence, untested


def hypothesis_statuses(
    hypotheses: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    untested: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return each hypothesis with how it ended: supported, refuted or untested."""
    untested_ids = {u["hypothesis_id"] for u in untested}
    results: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(hypotheses):
        hypothesis_id = hypothesis.get("id", f"h-{index}")
        found = [e for e in evidence if e.get("hypothesis_id") == hypothesis_id]
        if hypothesis_id in untested_ids or not found:
            status = "untested"
        elif any(e.get("supports_hypothesis") for e in found):
            status = "supported"
        else:
            status = "refuted"
        results.append(
            {"id": hypothesis_id, "title": hypothesis.get("title", ""), "status": status}
        )
    return results


def _untested(hypothesis: dict[str, Any], index: int, error: str) -> dict[str, Any]:
    """Describe a hypothesis whose evaluation failed, for synthesis."""
    return {
        "hypothesis_id": hypothesis.get("id", f"h-{index}"),
        "title": hypothesis.get("title", ""),
        "error": error,
    }


def _describe_failure(error: BaseException) -> str:
    """Describe why a child evaluation failed, without Temporal's wrapper errors."""
    while isinstance(error, ChildWorkflowError | ActivityError):
        cause = error.cause
        if cause is None:
            break
        error = cause
    return str(error) or type(error).__name__
