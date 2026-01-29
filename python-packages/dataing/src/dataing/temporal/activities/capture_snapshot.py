"""Capture snapshot activity for investigation workflow.

Captures investigation state at checkpoints for later hydration in JupyterLab.
This activity is fire-and-forget: failures are logged but don't block investigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from temporalio import activity

if TYPE_CHECKING:
    from dataing.core.snapshot import InvestigationSnapshot


class SnapshotStoreProtocol(Protocol):
    """Protocol for snapshot store used by capture_snapshot activity."""

    async def store(
        self,
        snapshot: InvestigationSnapshot,
        tenant_id: str,
    ) -> str:
        """Store a snapshot and return the storage path."""
        ...


@dataclass
class CaptureSnapshotInput:
    """Input for capture_snapshot activity."""

    investigation_id: str
    tenant_id: str
    checkpoint: str  # SnapshotCheckpoint value
    alert: dict[str, Any] | None = None
    hypotheses: list[dict[str, Any]] | None = None
    evidence: list[dict[str, Any]] | None = None
    synthesis: dict[str, Any] | None = None
    schema_snapshot: dict[str, Any] | None = None
    lineage_snapshot: dict[str, Any] | None = None
    sample_data_inline: dict[str, bytes] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class CaptureSnapshotResult:
    """Result from capture_snapshot activity."""

    success: bool
    storage_path: str | None = None
    error: str | None = None


def make_capture_snapshot_activity(
    snapshot_store: SnapshotStoreProtocol,
) -> Any:
    """Factory that creates capture_snapshot activity with injected dependencies.

    Args:
        snapshot_store: Store for persisting snapshots.

    Returns:
        The capture_snapshot activity function.
    """

    @activity.defn
    async def capture_snapshot(input: CaptureSnapshotInput) -> CaptureSnapshotResult:
        """Capture investigation state as a snapshot.

        This activity is designed to be fire-and-forget: it captures state
        without blocking the investigation workflow. Failures are logged
        and returned but don't raise exceptions.

        The snapshot includes:
        - Investigation identifiers and checkpoint
        - Alert data that triggered the investigation
        - Generated hypotheses
        - Collected evidence
        - Synthesis results (if complete)
        - Schema and lineage context
        - Sample data (small datasets inline, large via refs)
        - Environment metadata for reproducibility
        """
        from uuid import uuid4

        from dataing.core.snapshot import (
            EnvironmentMetadata,
            InvestigationSnapshot,
            LineageSnapshot,
            SnapshotCheckpoint,
        )

        try:
            # Parse checkpoint
            try:
                checkpoint = SnapshotCheckpoint(input.checkpoint)
            except ValueError:
                return CaptureSnapshotResult(
                    success=False,
                    error=f"Invalid checkpoint: {input.checkpoint}",
                )

            # Build lineage snapshot if provided
            lineage_snapshot = None
            if input.lineage_snapshot:
                lineage_snapshot = LineageSnapshot(
                    target=input.lineage_snapshot.get("target", ""),
                    upstream=input.lineage_snapshot.get("upstream", []),
                    downstream=input.lineage_snapshot.get("downstream", []),
                    depth=input.lineage_snapshot.get("depth", 2),
                )

            # Create snapshot
            snapshot = InvestigationSnapshot(
                snapshot_id=uuid4(),
                investigation_id=UUID(input.investigation_id),
                checkpoint=checkpoint,
                alert=input.alert,
                hypotheses=input.hypotheses or [],
                evidence=input.evidence or [],
                synthesis=input.synthesis,
                schema_snapshot=input.schema_snapshot,
                lineage_snapshot=lineage_snapshot,
                sample_data_inline=input.sample_data_inline or {},
                environment=EnvironmentMetadata.capture_current(),
                metadata=input.metadata or {},
            )

            # Store snapshot
            storage_path = await snapshot_store.store(snapshot, input.tenant_id)

            activity.logger.info(
                f"Captured snapshot for investigation {input.investigation_id} "
                f"at checkpoint {checkpoint.value}: {storage_path}"
            )

            return CaptureSnapshotResult(
                success=True,
                storage_path=storage_path,
            )

        except Exception as e:
            # Log but don't re-raise - snapshot capture is non-blocking
            activity.logger.warning(
                f"Failed to capture snapshot for investigation {input.investigation_id}: {e}"
            )
            return CaptureSnapshotResult(
                success=False,
                error=str(e),
            )

    return capture_snapshot
