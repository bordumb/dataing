"""Unit tests for evidence hash chain."""

from __future__ import annotations

from uuid import uuid4

import pytest

from dataing.core.evidence import (
    EvidenceKind,
    compute_content_hash,
    create_evidence_chain,
    is_hash_chain_enabled,
    verify_chain,
)

# ---------------------------------------------------------------------------
# Helper: build a valid chain of plain dicts (mimicking DB rows / export)
# ---------------------------------------------------------------------------


def _build_chain(length: int = 3) -> list[dict]:
    """Build a valid evidence chain of the given length."""
    items: list[dict] = []
    for i in range(length):
        seq = i + 1
        kind = "query_result"
        prev_hash = items[i - 1]["content_hash"] if i > 0 else None
        content = {"sql": f"SELECT {seq}", "row_count": seq, "execution_ms": 10}
        content_hash = compute_content_hash(
            seq=seq,
            kind=kind,
            prev_hash=prev_hash,
            content=content,
        )
        items.append(
            {
                "seq": seq,
                "kind": kind,
                "prev_hash": prev_hash,
                "content_hash": content_hash,
                "content": content,
            }
        )
    return items


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------


class TestComputeContentHash:
    """Tests for compute_content_hash."""

    def test_deterministic(self) -> None:
        """Same inputs always produce the same hash."""
        args = {"seq": 1, "kind": "query_result", "prev_hash": None, "content": {"a": 1}}
        assert compute_content_hash(**args) == compute_content_hash(**args)

    def test_hex_length(self) -> None:
        """Hash is a 64-character hex string (SHA-256)."""
        h = compute_content_hash(seq=1, kind="x", prev_hash=None, content={})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_seq_different_hash(self) -> None:
        """Changing seq produces a different hash."""
        base = {"kind": "query_result", "prev_hash": None, "content": {"a": 1}}
        assert compute_content_hash(seq=1, **base) != compute_content_hash(seq=2, **base)

    def test_different_kind_different_hash(self) -> None:
        """Changing kind produces a different hash."""
        base = {"seq": 1, "prev_hash": None, "content": {"a": 1}}
        h1 = compute_content_hash(kind="query_result", **base)
        h2 = compute_content_hash(kind="hypothesis", **base)
        assert h1 != h2

    def test_different_prev_hash_different_hash(self) -> None:
        """Changing prev_hash produces a different hash."""
        base = {"seq": 2, "kind": "query_result", "content": {"a": 1}}
        h1 = compute_content_hash(prev_hash="abc", **base)
        h2 = compute_content_hash(prev_hash="def", **base)
        assert h1 != h2

    def test_different_content_different_hash(self) -> None:
        """Changing content produces a different hash."""
        base = {"seq": 1, "kind": "query_result", "prev_hash": None}
        h1 = compute_content_hash(content={"a": 1}, **base)
        h2 = compute_content_hash(content={"a": 2}, **base)
        assert h1 != h2

    def test_key_order_does_not_matter(self) -> None:
        """RFC 8785 canonicalizes key order, so dict order is irrelevant."""
        base = {"seq": 1, "kind": "x", "prev_hash": None}
        h1 = compute_content_hash(content={"b": 2, "a": 1}, **base)
        h2 = compute_content_hash(content={"a": 1, "b": 2}, **base)
        assert h1 == h2


# ---------------------------------------------------------------------------
# verify_chain
# ---------------------------------------------------------------------------


class TestVerifyChain:
    """Tests for verify_chain."""

    def test_empty_chain_is_valid(self) -> None:
        """Empty list is a valid (trivial) chain."""
        valid, broken_seq, msg = verify_chain([])
        assert valid is True
        assert broken_seq is None
        assert msg is None

    def test_single_item_valid(self) -> None:
        """Single-item chain with correct hash is valid."""
        chain = _build_chain(1)
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is True

    def test_multi_item_valid(self) -> None:
        """Multi-item chain with correct linkage is valid."""
        chain = _build_chain(5)
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is True

    def test_broken_content_hash(self) -> None:
        """Tampered content_hash is detected."""
        chain = _build_chain(3)
        chain[1]["content_hash"] = "0" * 64
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is False
        assert broken_seq == 2
        assert "content_hash mismatch" in msg

    def test_broken_prev_hash(self) -> None:
        """Tampered prev_hash linkage is detected."""
        chain = _build_chain(3)
        chain[2]["prev_hash"] = "0" * 64
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is False
        assert broken_seq == 3
        assert "prev_hash mismatch" in msg

    def test_genesis_must_have_none_prev_hash(self) -> None:
        """First item with non-None prev_hash is invalid."""
        chain = _build_chain(1)
        chain[0]["prev_hash"] = "abc"
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is False
        assert broken_seq == 1
        assert "Genesis" in msg

    def test_reordered_items_detected(self) -> None:
        """Swapping items breaks the chain."""
        chain = _build_chain(3)
        chain[1], chain[2] = chain[2], chain[1]
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is False

    def test_tampered_content_detected(self) -> None:
        """Changing content without updating hash is detected."""
        chain = _build_chain(2)
        chain[0]["content"]["sql"] = "DROP TABLE users"
        valid, broken_seq, msg = verify_chain(chain)
        assert valid is False
        assert broken_seq == 1


# ---------------------------------------------------------------------------
# create_evidence_chain
# ---------------------------------------------------------------------------


class TestCreateEvidenceChain:
    """Tests for create_evidence_chain."""

    def test_returns_correct_kind(self) -> None:
        """Factory returns the concrete evidence subclass."""
        run_id = uuid4()
        ev = create_evidence_chain(
            run_id=run_id,
            kind=EvidenceKind.QUERY_RESULT,
            content={
                "sql": "SELECT 1",
                "row_count": 1,
                "execution_ms": 5,
            },
            seq=1,
        )
        assert ev.kind == EvidenceKind.QUERY_RESULT
        assert ev.seq == 1
        assert len(ev.content_hash) == 64

    def test_hash_chain_disabled_clears_prev_hash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When hash chain is disabled, prev_hash is always None."""
        monkeypatch.delenv("EVIDENCE_HASH_CHAIN", raising=False)
        ev = create_evidence_chain(
            run_id=uuid4(),
            kind=EvidenceKind.RUN_SUMMARY,
            content={
                "hypotheses_evaluated": 3,
                "queries_executed": 5,
                "duration_seconds": 12.0,
            },
            prev_hash="should_be_cleared",
            seq=2,
        )
        assert ev.prev_hash is None

    def test_hash_chain_enabled_keeps_prev_hash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When hash chain is enabled, prev_hash is preserved."""
        monkeypatch.setenv("EVIDENCE_HASH_CHAIN", "true")
        ev = create_evidence_chain(
            run_id=uuid4(),
            kind=EvidenceKind.RUN_SUMMARY,
            content={
                "hypotheses_evaluated": 3,
                "queries_executed": 5,
                "duration_seconds": 12.0,
            },
            prev_hash="abc123",
            seq=2,
        )
        assert ev.prev_hash == "abc123"

    def test_content_hash_matches_standalone_function(self) -> None:
        """content_hash on the model matches compute_content_hash()."""
        content = {"sql": "SELECT 1", "row_count": 1, "execution_ms": 5}
        ev = create_evidence_chain(
            run_id=uuid4(),
            kind=EvidenceKind.QUERY_RESULT,
            content=content,
            seq=1,
        )
        expected = compute_content_hash(
            seq=1,
            kind="query_result",
            prev_hash=None,
            content=content,
        )
        assert ev.content_hash == expected


# ---------------------------------------------------------------------------
# is_hash_chain_enabled
# ---------------------------------------------------------------------------


class TestIsHashChainEnabled:
    """Tests for is_hash_chain_enabled."""

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "YES"])
    def test_enabled_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        """Various truthy values enable the hash chain."""
        monkeypatch.setenv("EVIDENCE_HASH_CHAIN", value)
        assert is_hash_chain_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "", "anything"])
    def test_disabled_values(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        """Non-truthy values disable the hash chain."""
        monkeypatch.setenv("EVIDENCE_HASH_CHAIN", value)
        assert is_hash_chain_enabled() is False

    def test_unset_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing env var means disabled."""
        monkeypatch.delenv("EVIDENCE_HASH_CHAIN", raising=False)
        assert is_hash_chain_enabled() is False
