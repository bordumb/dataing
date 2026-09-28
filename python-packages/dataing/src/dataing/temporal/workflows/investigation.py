"""Investigation workflow definition for Temporal."""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    CancelledError,
    ChildWorkflowError,
)
from temporalio.workflow import ChildWorkflowCancellationType, ChildWorkflowHandle

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
    from dataing.temporal.errors import (
        INVESTIGATION_FAILED,
        LLM_MAX_ATTEMPTS,
        LLM_RETRY_POLICY,
        llm_failure_details,
    )
    from dataing.temporal.workflows.evaluate_hypothesis import (
        EvaluateHypothesisInput,
        EvaluateHypothesisWorkflow,
    )
    from dataing.temporal.workflows.steering import (
        RULED_OUT,
        Action,
        Decision,
        Phase,
        RunState,
        Steer,
        decide,
        next_hypothesis_id,
        steering_note,
        with_steering_notes,
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
    hypotheses_count: int
    hypotheses_evaluated: int
    evidence_count: int
    # Each hypothesis's id, title and status (pending, running, supported, refuted,
    # untested, ruled_out), and steers not applied yet, for the steering controls
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    pending_steers: list[dict[str, Any]] = field(default_factory=list)


class _RunFailed(Exception):
    """Ends a run as failed, with the reason (runs with the llm-failures-v1 patch).

    Raised inside the workflow and turned into an InvestigationFailed error by run(),
    after the failure is published. See docs/specs/0001_issue_chat.md §7.12.
    """

    def __init__(self, code: str, message: str, step: str) -> None:
        """Initialize with the failure's code, what to fix, and the step that failed."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.step = step

    def details(self) -> dict[str, str]:
        """Return the failure as outcome payloads and error details carry it."""
        return {"code": self.code, "message": self.message, "step": self.step}


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
    - steer: A person's steer, applied at the next checkpoint (runs with the
      steering-v1 patch; see steering.py)

    With the llm-failures-v1 patch, a run the model can't serve fails with the reason
    instead of concluding from nothing (docs/specs/0001_issue_chat.md §7.12).
    """

    def __init__(self) -> None:
        """Initialize workflow state."""
        self._cancelled = False
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
        # Hypotheses and how each ended, for get_status and steering
        self._hypotheses: list[dict[str, Any]] = []
        self._statuses: dict[str, str] = {}
        # Steering (docs/specs/0001_issue_chat.md §7.8), on for runs with steering-v1
        self._steering = False
        self._steers: list[Steer] = []
        self._notes: list[str] = []  # Context and exclusions added to later prompts
        self._ruled_out: dict[str, str] = {}  # Hypothesis id -> the person's reason
        self._synthesized = False
        self._resynthesize = False
        self._max_hypotheses = 5
        # Set while evaluating with steering
        self._running: dict[str, ChildWorkflowHandle[Any, Any]] = {}
        self._evidence: list[dict[str, Any]] = []
        self._untested: list[dict[str, Any]] = []
        self._input: InvestigationInput | None = None
        self._schema_info: dict[str, Any] = {}
        self._alert_summary = ""
        # LLM failures fail the run (llm-failures-v1)
        self._fail_runs = False
        self._stopped: set[str] = set()  # Hypotheses a person's stop left untested

    @workflow.signal
    def cancel_investigation(self) -> None:
        """Signal to cancel the investigation.

        The workflow will complete current activity and return with cancelled status.
        Child workflows will also be cancelled.
        """
        self._cancelled = True

    @workflow.signal
    def steer(self, payload: dict[str, Any]) -> None:
        """Queue a person's steer; the run applies it at its next checkpoint."""
        self._steers.append(Steer.from_payload(payload))

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
            hypotheses_count=self._hypotheses_count,
            hypotheses_evaluated=self._hypotheses_evaluated,
            evidence_count=self._evidence_count,
            hypotheses=[
                {
                    "id": _hypothesis_id(hypothesis, index),
                    "title": hypothesis.get("title", ""),
                    "status": self._statuses.get(_hypothesis_id(hypothesis, index), "pending"),
                }
                for index, hypothesis in enumerate(self._hypotheses)
            ],
            pending_steers=[
                {"steer_id": steer.steer_id, "kind": steer.kind} for steer in self._steers
            ],
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
        try:
            result = await self._investigate(input)
        except _RunFailed as failure:
            await self._fail(input, failure)
            raise ApplicationError(
                failure.message,
                failure.details(),
                type=INVESTIGATION_FAILED,
                non_retryable=True,
            ) from None
        if self._steering:
            # Steers the run never reached end here, so none stays pending
            rejection = "The investigation was cancelled" if result.status == "cancelled" else None
            while self._steers:
                await self._apply_steers(Phase.FINISHED, rejection=rejection)
        return result

    async def _investigate(self, input: InvestigationInput) -> InvestigationResult:
        """Run the investigation's steps and return its result."""
        # Initialize progress tracking
        self._investigation_id = input.investigation_id
        self._tenant_id = input.tenant_id
        self._current_step = "starting"
        self._progress = 0.0
        self._enable_snapshots = input.enable_snapshots
        self._snapshot_paths = []
        self._max_hypotheses = input.max_hypotheses
        self._steering = workflow.patched("steering-v1")
        self._fail_runs = workflow.patched("llm-failures-v1")

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

        # Steers sent before hypotheses exist shape their generation
        if self._steering:
            await self._apply_steers(Phase.BEFORE_HYPOTHESES)

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
                alert=self._alert(input.alert_data),
                schema_info=context.get("schema"),
                lineage_info=context.get("lineage"),
                matched_patterns=matched_patterns,
                max_hypotheses=input.max_hypotheses,
            )
            hypotheses_result = await self._llm_activity(
                "generate_hypotheses", hypotheses_input, timedelta(minutes=5)
            )
            hypotheses = hypotheses_result.get("hypotheses", [])
            if hypotheses_result.get("error"):
                err = hypotheses_result["error"]
                workflow.logger.warning(f"Hypothesis generation warning: {err}")
                if self._fail_runs:
                    raise _RunFailed("hypotheses_failed", err, "generate_hypotheses")
            if self._fail_runs and not hypotheses and not self._additions_queued():
                raise _RunFailed(
                    "no_hypotheses",
                    "The model proposed no hypotheses to test.",
                    "generate_hypotheses",
                )
        except CancelledError:
            return InvestigationResult(
                investigation_id=input.investigation_id,
                status="cancelled",
                context=context,
                snapshot_paths=self._snapshot_paths,
            )
        self._hypotheses_count = len(hypotheses) if hypotheses else 0
        self._hypotheses = list(hypotheses or [])
        self._statuses = {
            _hypothesis_id(hypothesis, index): "pending"
            for index, hypothesis in enumerate(self._hypotheses)
        }
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
        if self._steering:
            evidence, untested_hypotheses = await self._evaluate_with_steering(
                input, context.get("schema", {}), alert_summary
            )
            hypotheses = self._hypotheses
            self._hypotheses_count = len(hypotheses)
        else:
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
        if self._fail_runs:
            self._require_evidence(evidence, untested_hypotheses)

        # Step 5: Synthesize findings
        self._current_step = "synthesize"
        try:
            if self._steering:
                await self._apply_steers(Phase.SYNTHESIS)
            synthesize_result = await self._synthesize(
                input, alert_summary, hypotheses, evidence, untested_hypotheses
            )
            if self._steering:
                # Steers sent during synthesis: one re-synthesis covers all of them
                self._synthesized = True
                await self._apply_steers(Phase.SYNTHESIS)
                if self._resynthesize:
                    self._resynthesize = False
                    synthesize_result = await self._synthesize(
                        input, alert_summary, hypotheses, evidence, untested_hypotheses
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
                if self._fail_runs:
                    raise _RunFailed("synthesis_failed", synthesize_result["error"], "synthesize")
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
                try:
                    counter_result = await self._llm_activity(
                        "counter_analyze", counter_input, timedelta(minutes=5)
                    )
                except _RunFailed as failure:
                    # Counter-analysis only checks the conclusion: keep the conclusion
                    workflow.logger.warning(f"Counter-analysis failed: {failure.message}")
                    counter_result = {"error": failure.message, "error_code": failure.code}
                # Build counter_analysis dict from result fields
                counter_analysis = {
                    "alternative_explanations": counter_result.get("alternative_explanations", []),
                    "weaknesses": counter_result.get("weaknesses", []),
                    "confidence_adjustment": counter_result.get("confidence_adjustment", 0.0),
                    "recommendation": counter_result.get("recommendation", "accept"),
                }
                if counter_result.get("error"):
                    workflow.logger.warning(f"Counter-analysis warning: {counter_result['error']}")
                    if self._fail_runs:
                        counter_analysis = {
                            "error": {
                                "code": counter_result.get("error_code", "counter_analysis_failed"),
                                "message": counter_result["error"],
                            }
                        }
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
            "hypotheses": hypothesis_statuses(
                hypotheses, evidence, untested, ruled_out=set(self._ruled_out)
            ),
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

    def _alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Return the alert with the steering notes so far in its team brief."""
        steered: dict[str, Any] = with_steering_notes(alert, self._notes)
        return steered

    async def _synthesize(
        self,
        input: InvestigationInput,
        alert_summary: str,
        hypotheses: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        untested: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run the synthesize activity, keeping what people ruled out apart."""
        ruled_out = [
            {
                "hypothesis_id": _hypothesis_id(hypothesis, index),
                "title": hypothesis.get("title", ""),
                "reason": self._ruled_out[_hypothesis_id(hypothesis, index)],
            }
            for index, hypothesis in enumerate(hypotheses)
            if _hypothesis_id(hypothesis, index) in self._ruled_out
        ]
        synthesize_input = SynthesizeInput(
            investigation_id=input.investigation_id,
            evidence=[e for e in evidence if e.get("hypothesis_id") not in self._ruled_out],
            hypotheses=hypotheses,
            alert_summary=alert_summary,
            confidence_threshold=input.confidence_threshold,
            untested_hypotheses=[
                u for u in untested if u.get("hypothesis_id") not in self._ruled_out
            ],
            alert=self._alert(input.alert_data),
            ruled_out_hypotheses=ruled_out,
        )
        return await self._llm_activity("synthesize", synthesize_input, timedelta(minutes=5))

    async def _llm_activity(self, name: str, arg: Any, timeout: timedelta) -> dict[str, Any]:
        """Run an LLM activity.

        With llm-failures-v1 it retries per LLM_RETRY_POLICY, and a failure the model
        caused fails the run with the reason.
        """
        if not self._fail_runs:
            result: dict[str, Any] = await workflow.execute_activity(
                name, arg, start_to_close_timeout=timeout
            )
            return result
        try:
            result = await workflow.execute_activity(
                name, arg, start_to_close_timeout=timeout, retry_policy=LLM_RETRY_POLICY
            )
        except ActivityError as e:
            failure = _llm_run_failure(e, step=name)
            if failure is None:
                raise
            raise failure from None
        return result

    def _additions_queued(self) -> bool:
        """Return whether a person has asked for a hypothesis the run hasn't added yet."""
        return any(steer.kind == "add_hypothesis" for steer in self._steers)

    def _require_evidence(
        self, evidence: list[dict[str, Any]], untested: list[dict[str, Any]]
    ) -> None:
        """Fail the run when errors left every hypothesis untested.

        Hypotheses a person ruled out or stopped don't count: concluding without them
        was that person's choice.
        """
        if evidence:
            return
        failed = [
            u
            for u in untested
            if u["hypothesis_id"] not in self._stopped and u["hypothesis_id"] not in self._ruled_out
        ]
        if failed:
            raise _RunFailed(
                "no_evidence",
                f"No hypothesis could be tested. The first error: {failed[0]['error']}",
                "evaluate_hypotheses",
            )

    async def _fail(self, input: InvestigationInput, failure: _RunFailed) -> None:
        """End a failed run: stop its subagents, publish the failure, answer steers."""
        for handle in self._running.values():
            handle.cancel()
        self._running.clear()
        for hypothesis_id, status in list(self._statuses.items()):
            if status in ("pending", "running"):
                self._statuses[hypothesis_id] = "untested"
        self._current_step = "failed"
        self._is_complete = True
        payload = {
            "investigation_id": input.investigation_id,
            "tenant_id": input.tenant_id,
            "issue_id": (input.alert_data or {}).get("issue_id"),
            "failure": failure.details(),
            "hypotheses": [
                {
                    "id": _hypothesis_id(hypothesis, index),
                    "title": hypothesis.get("title", ""),
                    "status": self._statuses.get(_hypothesis_id(hypothesis, index), "untested"),
                }
                for index, hypothesis in enumerate(self._hypotheses)
            ],
        }
        try:
            await workflow.execute_activity(
                "publish_investigation_outcome",
                payload,
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
        except Exception as e:
            workflow.logger.warning(f"Publishing the failure failed (non-fatal): {e}")
        if self._steering:
            while self._steers:
                await self._apply_steers(Phase.FINISHED, rejection="The investigation failed")

    def _run_state(self) -> RunState:
        """Return what steer decisions need to know about the run."""
        return RunState(
            statuses=dict(self._statuses),
            titles={
                _hypothesis_id(hypothesis, index): hypothesis.get("title", "")
                for index, hypothesis in enumerate(self._hypotheses)
            },
            max_hypotheses=self._max_hypotheses,
            synthesized=self._synthesized,
        )

    async def _apply_steers(self, phase: Phase, *, rejection: str | None = None) -> None:
        """Apply every queued steer for the phase the run is in, recording each outcome.

        Steers that arrive while an outcome is being recorded are applied in the same
        pass. An add_hypothesis sent before hypotheses exist stays queued for the
        evaluation phase.

        Args:
            phase: Where the run is.
            rejection: Overrides the outcome of a rejected steer (e.g. cancelled).
        """
        deferred: list[Steer] = []
        while self._steers:
            steer = self._steers.pop(0)
            decision = decide(steer, phase, self._run_state())
            if decision.action is Action.DEFER:
                deferred.append(steer)
                continue
            applied, outcome = decision.applied, decision.outcome
            if applied:
                applied, outcome = await self._carry_out(steer, decision)
            elif rejection:
                outcome = rejection
            await self._record_steer(steer, phase, applied=applied, outcome=outcome)
        self._steers[:0] = deferred

    async def _carry_out(self, steer: Steer, decision: Decision) -> tuple[bool, str]:
        """Carry out an applied steer; return whether it applied and its outcome."""
        hypothesis_id = steer.hypothesis_id or ""
        if decision.action in (Action.NOTE, Action.EXCLUDE):
            self._notes.append(steering_note(steer))
        elif decision.action in (Action.CANCEL, Action.SET_ASIDE):
            self._statuses[hypothesis_id] = RULED_OUT
            self._ruled_out[hypothesis_id] = steer.text or "Ruled out by a person"
            handle = self._running.pop(hypothesis_id, None)
            if handle is not None:
                handle.cancel()
        elif decision.action is Action.ADD:
            return await self._add_hypothesis(steer)
        elif decision.action is Action.STOP:
            for running_id, handle in list(self._running.items()):
                handle.cancel()
                self._statuses[running_id] = "untested"
                self._stopped.add(running_id)
                index = self._index(running_id)
                self._untested.append(
                    _untested(
                        self._hypotheses[index],
                        index,
                        "Not tested: a person stopped the investigation before it finished",
                    )
                )
            self._running.clear()
        if decision.resynthesize:
            self._resynthesize = True
        return True, decision.outcome

    async def _add_hypothesis(self, steer: Steer) -> tuple[bool, str]:
        """Turn a person's text into a hypothesis and start a subagent for it."""
        hypothesis_id = next_hypothesis_id(list(self._statuses))
        try:
            formulated = await workflow.execute_activity(
                "formulate_hypothesis",
                {
                    "investigation_id": self._investigation_id,
                    "hypothesis_id": hypothesis_id,
                    "text": steer.text,
                    "alert_summary": self._alert_summary,
                },
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except ActivityError as e:
            return False, f"Could not add the hypothesis: {_describe_failure(e)}"
        hypothesis = {**formulated["hypothesis"], "id": hypothesis_id}
        self._hypotheses.append(hypothesis)
        self._statuses[hypothesis_id] = "pending"
        self._hypotheses_count = len(self._hypotheses)
        await self._start_child(len(self._hypotheses) - 1, hypothesis)
        return True, f"Started {hypothesis_id} '{hypothesis.get('title', '')}'"

    async def _record_steer(
        self, steer: Steer, phase: Phase, *, applied: bool, outcome: str
    ) -> None:
        """Record a steer's outcome on its row and in the issue thread. Non-fatal."""
        try:
            await workflow.execute_activity(
                "record_steer_outcome",
                {
                    "steer_id": steer.steer_id,
                    "investigation_id": self._investigation_id,
                    "kind": steer.kind,
                    "hypothesis_id": steer.hypothesis_id,
                    "status": "applied" if applied else "rejected",
                    "phase": phase.value,
                    "outcome": outcome,
                },
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
        except Exception as e:
            workflow.logger.warning(f"Recording steer {steer.steer_id} failed (non-fatal): {e}")

    def _index(self, hypothesis_id: str) -> int:
        """Return the position of a hypothesis in the run's list."""
        for index, hypothesis in enumerate(self._hypotheses):
            if _hypothesis_id(hypothesis, index) == hypothesis_id:
                return index
        raise KeyError(hypothesis_id)

    async def _start_child(self, index: int, hypothesis: dict[str, Any]) -> None:
        """Start the subagent that evaluates one hypothesis."""
        assert self._input is not None
        child_input = EvaluateHypothesisInput(
            investigation_id=self._input.investigation_id,
            hypothesis_index=index,
            hypothesis=hypothesis,
            schema_info=self._schema_info,
            alert_summary=self._alert_summary,
            tenant_id=self._input.tenant_id,
            datasource_id=self._input.datasource_id,
            alert=self._alert(self._input.alert_data),
        )
        handle = await workflow.start_child_workflow(
            EvaluateHypothesisWorkflow.run,
            child_input,
            id=f"{workflow.info().workflow_id}-hypothesis-{index}",
            # A ruled-out subagent is left to stop on its own; the run moves on
            cancellation_type=ChildWorkflowCancellationType.TRY_CANCEL,
        )
        self._child_handles.append(handle)
        self._running[_hypothesis_id(hypothesis, index)] = handle
        self._statuses[_hypothesis_id(hypothesis, index)] = "running"

    def _collect(self, hypothesis_id: str, handle: ChildWorkflowHandle[Any, Any]) -> None:
        """Record how a finished subagent's hypothesis ended."""
        index = self._index(hypothesis_id)
        hypothesis = self._hypotheses[index]
        try:
            result = handle.result()
        except BaseException as e:  # A failed or cancelled child leaves it untested
            reason = _describe_failure(e)
            workflow.logger.warning(f"Child workflow failed: {reason}")
            self._untested.append(_untested(hypothesis, index, f"Evaluation failed: {reason}"))
            self._statuses[hypothesis_id] = "untested"
            # The model fails every subagent the same way, so the run stops here
            if self._fail_runs and (failure := _llm_run_failure(e)) is not None:
                raise failure from None
            return
        self._hypotheses_evaluated += 1
        if result.error:
            workflow.logger.warning(f"Hypothesis {hypothesis_id} evaluation error: {result.error}")
            self._untested.append(_untested(hypothesis, index, result.error))
            self._statuses[hypothesis_id] = "untested"
            return
        self._evidence.extend(result.evidence)
        if not result.evidence:
            self._statuses[hypothesis_id] = "untested"
        elif any(e.get("supports_hypothesis") for e in result.evidence):
            self._statuses[hypothesis_id] = "supported"
        else:
            self._statuses[hypothesis_id] = "refuted"

    async def _evaluate_with_steering(
        self, input: InvestigationInput, schema_info: dict[str, Any], alert_summary: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Evaluate hypotheses in child workflows, applying steers as they arrive.

        The loop wakes when a subagent finishes or a steer is queued, so a person
        can rule out, add or stop hypotheses while the others keep running.

        Returns:
            Tuple of (evidence from successful evaluations, untested hypotheses).
        """
        self._input = input
        self._schema_info = schema_info
        self._alert_summary = alert_summary
        self._child_handles = []
        self._running = {}
        self._evidence = []
        self._untested = []

        # Steers queued so far apply before any subagent starts
        await self._apply_steers(Phase.EVALUATION)
        for index, hypothesis in enumerate(list(self._hypotheses)):
            if self._cancelled:
                break
            if self._statuses.get(_hypothesis_id(hypothesis, index)) == "pending":
                await self._start_child(index, hypothesis)

        while self._running and not self._cancelled:
            await workflow.wait_condition(
                lambda: (
                    self._cancelled
                    or bool(self._steers)
                    or any(handle.done() for handle in self._running.values())
                )
            )
            for hypothesis_id, handle in list(self._running.items()):
                if handle.done():
                    del self._running[hypothesis_id]
                    self._collect(hypothesis_id, handle)
            if self._steers and not self._cancelled:
                await self._apply_steers(Phase.EVALUATION)

        if self._cancelled:
            await self._cancel_children()
            return [], []
        return self._evidence, self._untested

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
    ruled_out: set[str] | frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Return each hypothesis with how it ended.

    That is supported or refuted by evidence, ruled out by a person, or untested.
    """
    untested_ids = {u["hypothesis_id"] for u in untested}
    results: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(hypotheses):
        hypothesis_id = _hypothesis_id(hypothesis, index)
        found = [e for e in evidence if e.get("hypothesis_id") == hypothesis_id]
        if hypothesis_id in ruled_out:
            status = RULED_OUT
        elif hypothesis_id in untested_ids or not found:
            status = "untested"
        elif any(e.get("supports_hypothesis") for e in found):
            status = "supported"
        else:
            status = "refuted"
        results.append(
            {"id": hypothesis_id, "title": hypothesis.get("title", ""), "status": status}
        )
    return results


def _hypothesis_id(hypothesis: dict[str, Any], index: int) -> str:
    """Return a hypothesis's id, or a positional one when it has none."""
    return str(hypothesis.get("id", f"h-{index}"))


def _untested(hypothesis: dict[str, Any], index: int, error: str) -> dict[str, Any]:
    """Describe a hypothesis whose evaluation failed, for synthesis."""
    return {
        "hypothesis_id": _hypothesis_id(hypothesis, index),
        "title": hypothesis.get("title", ""),
        "error": error,
    }


def _llm_run_failure(error: BaseException, step: str | None = None) -> _RunFailed | None:
    """Return the run failure for an activity or child failure the model caused."""
    details = llm_failure_details(error)
    if details is None:
        return None
    message = details["message"]
    if details["retried"]:
        message = f"{message} It kept failing after {LLM_MAX_ATTEMPTS} attempts; try again later."
    return _RunFailed(details["code"], message, step or details["activity"] or "evaluate")


def _describe_failure(error: BaseException) -> str:
    """Describe why a child evaluation failed, without Temporal's wrapper errors."""
    while isinstance(error, ChildWorkflowError | ActivityError):
        cause = error.cause
        if cause is None:
            break
        error = cause
    return str(error) or type(error).__name__
