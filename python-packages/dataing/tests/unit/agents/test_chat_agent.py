"""Tests for the issue chat agent (docs/specs/0001_issue_chat.md §7.4-§7.6).

The model is a scripted pydantic-ai FunctionModel, so no request leaves the process.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from dataing.adapters.datasource.gateway import UserPrincipal
from dataing.agents.chat import (
    ChatDeps,
    build_chat_agent,
    build_history,
    build_instructions,
    run_turn,
)
from dataing.core.agent_query import (
    AgentQueryError,
    AgentQueryErrorCode,
    AgentQueryResult,
    QueryModelView,
)

models.ALLOW_MODEL_REQUESTS = False

ISSUE = {
    "id": "7a1c",
    "number": 42,
    "title": "Completed orders dropped",
    "status": "in_progress",
    "dataset_id": "analytics.public.orders",
    "context": {"column": "status"},
}


class FakeServices:
    """In-memory ChatServices."""

    def __init__(self, query_error: AgentQueryError | None = None) -> None:
        """Initialize with an optional error every query raises."""
        self.query_error = query_error
        self.queries: list[str] = []
        self.saved: list[tuple[str, Any]] = []

    async def issue_context(self) -> dict[str, Any]:
        return {"issue": ISSUE, "runs": []}

    async def run_query(self, sql: str, purpose: str) -> AgentQueryResult:
        self.queries.append(sql)
        if self.query_error:
            raise self.query_error
        view = QueryModelView(
            columns=[{"name": "region"}, {"name": "n"}],
            rows=[{"region": "us", "n": 3}],
            row_count=1,
            truncated=False,
            column_stats={},
        )
        return AgentQueryResult(
            sql=sql,
            dialect="postgres",
            purpose=purpose,
            columns=[{"name": "region"}, {"name": "n"}],
            rows=[{"region": "us", "n": 3}],
            row_count=1,
            truncated=False,
            duration_ms=12,
            model_view=view,
        )

    async def save_query_result(
        self, tool_call_id: str, sql: str, result: AgentQueryResult | None, error: str | None
    ) -> uuid.UUID:
        self.saved.append((tool_call_id, result or error))
        return uuid.uuid4()

    async def list_tables(self, pattern: str | None) -> dict[str, Any]:
        return {"tables": [{"native_path": "public.orders"}], "truncated": False}

    async def describe_table(self, table: str) -> dict[str, Any]:
        return {"name": table, "columns": [{"name": "status", "type": "text"}]}

    async def get_investigation(self, run_id: str) -> dict[str, Any] | None:
        return {"id": run_id, "status": "running", "hypotheses": []}


def _deps(services: FakeServices) -> ChatDeps:
    return ChatDeps(
        principal=UserPrincipal(
            user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), datasource_id=uuid.uuid4()
        ),
        services=services,
    )


def _scripted(*turns: list[Any]) -> FunctionModel:
    """Return a streaming model that plays one scripted turn per model request."""
    script = list(turns)

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
        for chunk in script.pop(0):
            yield chunk

    return FunctionModel(stream_function=stream)


def _tool_call(name: str, args: dict[str, Any], call_id: str = "call-1") -> dict[int, Any]:
    return {0: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=call_id)}


class TestRunTurn:
    """run_turn streams text and records tool calls."""

    async def test_text_streams_in_order(self) -> None:
        """Every text delta reaches the callback in order, and the full text is returned."""
        agent = build_chat_agent(_scripted(["All ", "regions ", "dropped."]))
        deltas: list[str] = []

        result = await run_turn(
            agent, _deps(FakeServices()), "is it every region?", [], deltas.append
        )

        assert "".join(deltas) == "All regions dropped."
        assert result.text == "All regions dropped."

    async def test_query_tool_call_is_recorded_and_snapshotted(self) -> None:
        """A run_query call is executed, saved, and recorded with a summary."""
        services = FakeServices()
        agent = build_chat_agent(
            _scripted(
                [_tool_call("run_query", {"sql": "SELECT 1", "purpose": "count by region"})],
                ["Only us has rows."],
            )
        )

        result = await run_turn(agent, _deps(services), "count by region", [], lambda _: None)

        assert services.queries == ["SELECT 1"]
        assert len(services.saved) == 1
        (call,) = result.tool_calls
        assert call.tool == "run_query"
        assert call.input == {"sql": "SELECT 1", "purpose": "count by region"}
        assert call.status == "ok"
        assert call.query_result_id is not None
        assert "1 row" in call.summary
        assert result.text == "Only us has rows."

    async def test_missing_credentials_is_a_structured_tool_result(self) -> None:
        """credentials_missing reaches the model as data, not an exception."""
        error = AgentQueryError(
            AgentQueryErrorCode.CREDENTIALS_MISSING,
            "No credentials",
            {"action_url": "/settings/datasources/x/credentials"},
        )
        seen: list[str] = []

        async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
            if len(messages) == 1:
                yield _tool_call("run_query", {"sql": "SELECT 1", "purpose": "p"})
            else:
                seen.append(str(messages[-1]))
                yield "You need to add credentials first."

        agent = build_chat_agent(FunctionModel(stream_function=stream))
        result = await run_turn(
            agent, _deps(FakeServices(query_error=error)), "q", [], lambda _: None
        )

        assert "credentials_missing" in seen[0]
        (call,) = result.tool_calls
        assert call.status == "error"
        assert call.error_code == "credentials_missing"

    async def test_propose_steer_has_no_side_effects(self) -> None:
        """A steer proposal is recorded for a person to send; nothing is sent."""
        services = FakeServices()
        agent = build_chat_agent(
            _scripted(
                [
                    _tool_call(
                        "propose_steer",
                        {"run_id": "r1", "kind": "add_context", "text": "v2 shipped 09:00"},
                    )
                ],
                ["Here is a steer you can send."],
            )
        )

        result = await run_turn(agent, _deps(services), "tell it v2 shipped", [], lambda _: None)

        assert result.proposals == [
            {
                "run_id": "r1",
                "kind": "add_context",
                "text": "v2 shipped 09:00",
                "hypothesis_id": None,
            }
        ]
        assert services.queries == []

    async def test_invalid_steer_kind_is_rejected(self) -> None:
        """Only the four steer kinds can be proposed."""
        agent = build_chat_agent(
            _scripted(
                [_tool_call("propose_steer", {"run_id": "r1", "kind": "delete", "text": "x"})],
                [_tool_call("propose_steer", {"run_id": "r1", "kind": "delete", "text": "x"})],
                ["ok"],
                ["ok"],
            )
        )

        result = await run_turn(agent, _deps(FakeServices()), "q", [], lambda _: None)

        assert result.proposals == []


class TestPrompt:
    """Prompt assembly is deterministic so the provider can cache the prefix."""

    def test_instructions_are_byte_stable(self) -> None:
        """The same issue renders to identical instructions regardless of key order."""
        shuffled = dict(reversed(list(ISSUE.items())))

        assert build_instructions(ISSUE) == build_instructions(shuffled)
        assert "Completed orders dropped" in build_instructions(ISSUE)

    def test_history_labels_people_and_merges_consecutive_comments(self) -> None:
        """Human comments carry the author's name; consecutive ones form one request."""
        history = build_history(
            [
                {"author_kind": "user", "author_name": "Maya", "body_md": "is it every region?"},
                {
                    "author_kind": "user",
                    "author_name": "Raj",
                    "body_md": "dashboard counts completed",
                },
                {
                    "author_kind": "agent",
                    "body_md": "Yes, every region.",
                    "payload": {
                        "tool_calls": [
                            {"tool": "run_query", "summary": "4 rows", "query_result_id": "q1"}
                        ]
                    },
                },
            ]
        )

        assert isinstance(history[0], ModelRequest)
        parts = [p.content for p in history[0].parts if isinstance(p, UserPromptPart)]
        assert parts == ["Maya: is it every region?", "Raj: dashboard counts completed"]
        assert isinstance(history[1], ModelResponse)
        assert "run_query" in str(history[1].parts[0].content)
        assert "q1" in str(history[1].parts[0].content)

    def test_long_history_keeps_summary_and_recent_turns(self) -> None:
        """Beyond the window, only the thread summary and the latest messages are sent."""
        messages = [
            {"author_kind": "user", "author_name": "Maya", "body_md": f"message {i}"}
            for i in range(100)
        ]

        history = build_history(messages, summary="Earlier: ruled out regions.", max_messages=10)

        text = str(history)
        assert "Earlier: ruled out regions." in text
        assert "message 99" in text
        assert "message 50" not in text

    def test_system_events_and_deleted_messages_are_skipped(self) -> None:
        """Deleted comments never reach the model."""
        history = build_history(
            [
                {"author_kind": "user", "author_name": "Maya", "body_md": "", "deleted": True},
                {"author_kind": "system", "body_md": "Status changed from open to triaged"},
            ]
        )

        assert "Status changed" in str(history)
        assert len(history) == 1


@pytest.fixture(autouse=True)
def _no_model_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)


class TestBriefDrafting:
    """The drafting agent returns a structured BriefDraft from the thread."""

    async def test_draft_is_parsed_from_a_json_reply_without_forcing_a_tool(self) -> None:
        """The draft comes back as JSON text, not through a forced output tool.

        An output tool makes pydantic-ai send tool_choice "any", which Claude Opus 5.5
        rejects with a 400; with text output allowed it sends "auto".
        """
        from pydantic_ai.messages import ModelResponse, TextPart

        from dataing.agents.chat import build_brief_agent, draft_brief

        seen: list[AgentInfo] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            seen.append(info)
            draft = {
                "symptom": "Orders dropped",
                "findings": [{"statement": "Only app_v2", "source_seq": 4}],
                "leads": ["app_v2 deploy"],
            }
            return ModelResponse(parts=[TextPart(json.dumps(draft))])

        agent = build_brief_agent(FunctionModel(respond))
        history = build_history(
            [{"author_kind": "user", "author_name": "Maya", "body_md": "only app_v2?", "seq": 4}]
        )

        draft, usage = await draft_brief(agent, history, instructions="issue block")

        assert (seen[0].output_tools, seen[0].allow_text_output) == ([], True)
        assert draft.symptom == "Orders dropped"
        assert draft.findings[0].source_seq == 4
        assert usage.requests == 1

    def test_history_numbers_messages_for_citation(self) -> None:
        """Messages with a seq are labelled #seq so the draft can cite them."""
        history = build_history(
            [{"author_kind": "user", "author_name": "Maya", "body_md": "hi", "seq": 7}]
        )

        assert "#7 Maya: hi" in str(history)
