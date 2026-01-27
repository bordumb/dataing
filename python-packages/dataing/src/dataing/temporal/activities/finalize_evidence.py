"""Finalize evidence chain activity for investigation workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from temporalio import activity

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase


@dataclass
class FinalizeEvidenceChainInput:
    """Input for finalize evidence chain activity."""

    investigation_id: str
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    synthesis: dict[str, Any] = field(default_factory=dict)


@dataclass
class FinalizeEvidenceChainResult:
    """Result from finalize evidence chain activity."""

    root_hash: str | None = None
    evidence_count: int = 0
    error: str | None = None


def _sort_evidence_deterministically(
    evidence: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    synthesis: dict[str, Any],
) -> list[dict[str, Any]]:
    """Sort evidence items into a deterministic order for hash chain.

    Order:
    1. Hypothesis items grouped by hypothesis_id (alphabetical).
    2. Within each hypothesis: query_result, then interpretation.
    3. Synthesis/run_summary at the end.

    Args:
        evidence: Raw evidence dicts from parallel evaluation.
        hypotheses: Hypothesis dicts for ordering reference.
        synthesis: Synthesis dict to append as final evidence.

    Returns:
        Deterministically sorted list of evidence dicts.
    """
    # Build lookup of hypothesis_id ordering
    hypothesis_ids = sorted(
        {e.get("hypothesis_id", "") for e in evidence if e.get("hypothesis_id")}
    )

    # Evidence type ordering within a hypothesis group
    type_order = {
        "query_result": 0,
        "metric_calculation": 1,
        "schema_snapshot": 2,
        "lineage_trace": 3,
        "hypothesis": 4,
    }

    def sort_key(item: dict[str, Any]) -> tuple[int, str, int, str]:
        """Sort key: (group, hypothesis_id, type_order, sql/content for stability)."""
        hyp_id = item.get("hypothesis_id", "")
        kind = item.get("kind", item.get("type", ""))

        # Hypothesis group index (items without hypothesis_id go to end)
        if hyp_id and hyp_id in hypothesis_ids:
            group = hypothesis_ids.index(hyp_id)
        else:
            group = len(hypothesis_ids)

        t_order = type_order.get(kind, 99)
        # Stable tiebreaker
        stable = item.get("sql", item.get("metric_name", ""))
        return (group, hyp_id, t_order, stable)

    sorted_evidence = sorted(evidence, key=sort_key)

    # Append synthesis as run_summary if present
    if synthesis and synthesis.get("root_cause"):
        sorted_evidence.append(
            {
                "kind": "run_summary",
                "content": synthesis,
            }
        )

    return sorted_evidence


def make_finalize_evidence_chain_activity(
    app_db: AppDatabase,
) -> Any:
    """Factory that creates finalize evidence chain activity.

    Args:
        app_db: Application database for persisting evidence.

    Returns:
        The finalize_evidence_chain activity function.
    """

    @activity.defn
    async def finalize_evidence_chain(
        input: FinalizeEvidenceChainInput,
    ) -> FinalizeEvidenceChainResult:
        """Build hash chain from evidence and persist to database."""
        from uuid import UUID

        from dataing.core.evidence import (
            compute_content_hash,
            is_hash_chain_enabled,
        )
        from dataing.core.json_utils import to_json_safe

        if not input.evidence and not input.synthesis:
            return FinalizeEvidenceChainResult(
                root_hash=None,
                evidence_count=0,
            )

        try:
            # Sort deterministically
            sorted_items = _sort_evidence_deterministically(
                evidence=input.evidence,
                hypotheses=input.hypotheses,
                synthesis=input.synthesis,
            )

            if not sorted_items:
                return FinalizeEvidenceChainResult(
                    root_hash=None,
                    evidence_count=0,
                )

            investigation_id = UUID(input.investigation_id)
            chain_enabled = is_hash_chain_enabled()

            # Build hash chain
            prev_hash: str | None = None
            evidence_count = 0

            for i, item in enumerate(sorted_items):
                seq = i + 1
                kind = item.get("kind", item.get("type", "unknown"))

                # Extract content (everything except chain metadata)
                content = to_json_safe({k: v for k, v in item.items() if k not in ("kind", "type")})

                # Compute hash (always compute, even if chain disabled)
                effective_prev_hash = prev_hash if chain_enabled else None
                content_hash = compute_content_hash(
                    seq=seq,
                    kind=kind,
                    prev_hash=effective_prev_hash,
                    content=content,
                )

                # Store evidence
                from dataing.adapters.db.sdk_repository import EvidenceRepository

                repo = EvidenceRepository(app_db)
                await repo.store_evidence(
                    run_id=investigation_id,
                    seq=seq,
                    kind=kind,
                    content=content,
                    content_hash=content_hash,
                    prev_hash=effective_prev_hash,
                )

                prev_hash = content_hash
                evidence_count += 1

            root_hash = prev_hash

            # Store root_hash on investigation record
            if root_hash:
                await app_db.execute(
                    """
                    UPDATE investigations
                    SET root_hash = $2
                    WHERE id = $1
                    """,
                    investigation_id,
                    root_hash,
                )

            return FinalizeEvidenceChainResult(
                root_hash=root_hash,
                evidence_count=evidence_count,
            )

        except Exception as e:
            activity.logger.error(f"Failed to finalize evidence chain: {e}")
            return FinalizeEvidenceChainResult(
                root_hash=None,
                evidence_count=0,
                error=f"Evidence chain finalization failed: {e}",
            )

    return finalize_evidence_chain
