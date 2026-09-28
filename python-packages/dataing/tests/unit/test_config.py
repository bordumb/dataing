"""Settings defaults read from the environment."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dataing.config import CHAT_MODEL, INVESTIGATION_MODEL, Settings

SOURCES = [
    Path(__file__).parents[2] / "src" / "dataing",
    Path(__file__).parents[4] / "dataing-ee" / "src" / "dataing_ee",
]
MODEL_ID = re.compile(r"""["']claude-[a-z0-9.-]+["']""")


def test_chat_agent_defaults_to_claude_opus_5_5(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chat turns and brief drafting run on Claude Opus 5.5 unless CHAT_AGENT_MODEL is set."""
    monkeypatch.delenv("CHAT_AGENT_MODEL", raising=False)

    assert Settings().chat_agent_model == CHAT_MODEL == "claude-opus-5-5"


def test_investigations_default_to_claude_sonnet_5_5(monkeypatch: pytest.MonkeyPatch) -> None:
    """Investigations run on Claude Sonnet 5.5 unless LLM_MODEL is set."""
    monkeypatch.delenv("LLM_MODEL", raising=False)

    assert Settings().llm_model == INVESTIGATION_MODEL == "claude-sonnet-5-5"


@pytest.mark.parametrize("variable", ["LLM_MODEL", "CHAT_AGENT_MODEL"])
def test_an_empty_model_variable_means_the_default(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    """An unset variable arrives empty from docker compose; it keeps the default."""
    monkeypatch.setenv(variable, "")

    settings = Settings()

    assert (settings.llm_model, settings.chat_agent_model) == (INVESTIGATION_MODEL, CHAT_MODEL)


def test_a_model_variable_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployments can pick another model without a code change."""
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    assert Settings().llm_model == "claude-haiku-4-5-20251001"


def test_config_is_the_only_place_that_names_a_model() -> None:
    """Model ids live in dataing.config; everything else reads them from there.

    A retired model hard-coded as a default elsewhere once broke every investigation.
    """
    named = [
        f"{path.relative_to(source.parent)}: {match}"
        for source in SOURCES
        for path in sorted(source.rglob("*.py"))
        if path.name != "config.py" or path.parent != SOURCES[0]
        for match in MODEL_ID.findall(path.read_text())
    ]

    assert named == []
