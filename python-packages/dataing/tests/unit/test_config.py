"""Settings defaults read from the environment."""

from __future__ import annotations

import pytest

from dataing.config import Settings


def test_chat_agent_defaults_to_claude_opus_5_5(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chat turns and brief drafting run on Claude Opus 5.5 unless CHAT_AGENT_MODEL is set."""
    monkeypatch.delenv("CHAT_AGENT_MODEL", raising=False)

    assert Settings().chat_agent_model == "claude-opus-5-5"
