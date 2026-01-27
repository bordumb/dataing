"""Unit tests for evidence chain finalization activity."""

from __future__ import annotations

from dataing.core.evidence import compute_content_hash, verify_chain
from dataing.temporal.activities.finalize_evidence import (
    _sort_evidence_deterministically,
)

# ---------------------------------------------------------------------------
# _sort_evidence_deterministically
# ---------------------------------------------------------------------------


class TestSortEvidenceDeterministically:
    """Tests for deterministic evidence sorting."""

    def test_empty_evidence(self) -> None:
        """Empty evidence returns empty list (no synthesis if empty)."""
        result = _sort_evidence_deterministically([], [], {})
        assert result == []

    def test_groups_by_hypothesis_id(self) -> None:
        """Evidence is grouped by hypothesis_id alphabetically."""
        evidence = [
            {"hypothesis_id": "h-b", "kind": "query_result", "sql": "SELECT 2"},
            {"hypothesis_id": "h-a", "kind": "query_result", "sql": "SELECT 1"},
        ]
        result = _sort_evidence_deterministically(evidence, [], {})
        assert result[0]["hypothesis_id"] == "h-a"
        assert result[1]["hypothesis_id"] == "h-b"

    def test_type_order_within_group(self) -> None:
        """Within a hypothesis group, query_result comes before hypothesis."""
        evidence = [
            {"hypothesis_id": "h-a", "kind": "hypothesis", "text": "hyp"},
            {"hypothesis_id": "h-a", "kind": "query_result", "sql": "SELECT 1"},
        ]
        result = _sort_evidence_deterministically(evidence, [], {})
        assert result[0]["kind"] == "query_result"
        assert result[1]["kind"] == "hypothesis"

    def test_synthesis_appended_at_end(self) -> None:
        """Synthesis is appended as run_summary at the end."""
        evidence = [
            {"hypothesis_id": "h-a", "kind": "query_result", "sql": "SELECT 1"},
        ]
        synthesis = {"root_cause": "Schema change", "confidence": 0.9}
        result = _sort_evidence_deterministically(evidence, [], synthesis)
        assert len(result) == 2
        assert result[-1]["kind"] == "run_summary"
        assert result[-1]["content"] == synthesis

    def test_synthesis_not_appended_if_empty(self) -> None:
        """Empty synthesis or no root_cause means no run_summary."""
        evidence = [
            {"hypothesis_id": "h-a", "kind": "query_result", "sql": "SELECT 1"},
        ]
        result = _sort_evidence_deterministically(evidence, [], {})
        assert len(result) == 1

    def test_deterministic_across_calls(self) -> None:
        """Multiple calls produce the same order."""
        evidence = [
            {"hypothesis_id": "h-c", "kind": "query_result", "sql": "SELECT 3"},
            {"hypothesis_id": "h-a", "kind": "hypothesis", "text": "hyp"},
            {"hypothesis_id": "h-b", "kind": "query_result", "sql": "SELECT 2"},
            {"hypothesis_id": "h-a", "kind": "query_result", "sql": "SELECT 1"},
        ]
        r1 = _sort_evidence_deterministically(evidence, [], {})
        r2 = _sort_evidence_deterministically(evidence, [], {})
        assert r1 == r2


# ---------------------------------------------------------------------------
# Hash chain construction (integration with compute_content_hash + verify_chain)
# ---------------------------------------------------------------------------


class TestHashChainConstruction:
    """Test that sorted evidence can form a valid hash chain."""

    def test_build_and_verify_chain(self) -> None:
        """Build a chain from sorted evidence and verify it."""
        evidence = [
            {"hypothesis_id": "h-a", "kind": "query_result", "sql": "SELECT 1"},
            {"hypothesis_id": "h-a", "kind": "hypothesis", "text": "null spike"},
            {"hypothesis_id": "h-b", "kind": "query_result", "sql": "SELECT 2"},
        ]
        synthesis = {"root_cause": "Schema change", "confidence": 0.9}

        sorted_items = _sort_evidence_deterministically(evidence, [], synthesis)

        # Build hash chain from sorted items (mirroring activity logic)
        chain: list[dict] = []
        prev_hash = None
        for i, item in enumerate(sorted_items):
            seq = i + 1
            kind = item.get("kind", "unknown")
            content = {k: v for k, v in item.items() if k not in ("kind", "type")}
            content_hash = compute_content_hash(
                seq=seq,
                kind=kind,
                prev_hash=prev_hash,
                content=content,
            )
            chain.append(
                {
                    "seq": seq,
                    "kind": kind,
                    "prev_hash": prev_hash,
                    "content_hash": content_hash,
                    "content": content,
                }
            )
            prev_hash = content_hash

        # Verify the chain
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is True
        assert broken_seq is None
        assert len(chain) == 4  # 3 evidence + 1 synthesis
        assert chain[-1]["kind"] == "run_summary"
        # root_hash is the last item's content_hash
        assert chain[-1]["content_hash"] == prev_hash

    def test_chain_with_no_synthesis(self) -> None:
        """Chain without synthesis still verifies."""
        evidence = [
            {"hypothesis_id": "h-a", "kind": "query_result", "sql": "SELECT 1"},
        ]
        sorted_items = _sort_evidence_deterministically(evidence, [], {})

        chain: list[dict] = []
        prev_hash = None
        for i, item in enumerate(sorted_items):
            seq = i + 1
            kind = item.get("kind", "unknown")
            content = {k: v for k, v in item.items() if k not in ("kind", "type")}
            content_hash = compute_content_hash(
                seq=seq,
                kind=kind,
                prev_hash=prev_hash,
                content=content,
            )
            chain.append(
                {
                    "seq": seq,
                    "kind": kind,
                    "prev_hash": prev_hash,
                    "content_hash": content_hash,
                    "content": content,
                }
            )
            prev_hash = content_hash

        valid, broken_seq, msg = verify_chain(chain)
        assert valid is True
