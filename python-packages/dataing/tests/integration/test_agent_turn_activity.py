"""run_agent_turn and mark_turn_failed against the migrated schema.

The model is a scripted FunctionModel and queries go to a fake query service, so
nothing leaves the process; everything else (threads, snapshots, statuses) is real.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic_ai import models
from pydantic_ai.messages import ModelMessage, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from temporalio.testing import ActivityEnvironment

from dataing.adapters.datasource.gateway import UserPrincipal
from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.agents.chat import build_chat_agent
from dataing.core.agent_query import AgentQueryResult, QueryModelView
from dataing.temporal.activities.agent_turn import (
    make_mark_turn_failed_activity,
    make_run_agent_turn_activity,
)

pytestmark = pytest.mark.integration


class FakeQueries:
    """Stands in for AgentQueryService."""

    def __init__(self) -> None:
        """Initialize with no queries run."""
        self.principals: list[UserPrincipal] = []

    async def run(self, principal: UserPrincipal, sql: str, purpose: str) -> AgentQueryResult:
        self.principals.append(principal)
        rows = [{"region": "us", "n": 3}]
        view = QueryModelView(
            columns=[{"name": "region"}, {"name": "n"}],
            rows=rows,
            row_count=1,
            truncated=False,
            column_stats={},
        )
        return AgentQueryResult(
            sql=sql,
            dialect="postgres",
            purpose=purpose,
            columns=[{"name": "region"}, {"name": "n"}],
            rows=rows,
            row_count=1,
            truncated=False,
            duration_ms=4,
            model_view=view,
        )


def _agent_factory() -> Any:
    """Return a factory for an agent that runs one query, then answers."""

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[Any]:
        last = messages[-1]
        answered = isinstance(last, ModelRequest) and any(
            isinstance(part, ToolReturnPart) for part in last.parts
        )
        if not answered:
            yield {
                0: DeltaToolCall(
                    name="run_query",
                    json_args=json.dumps({"sql": "SELECT region, n", "purpose": "by region"}),
                    tool_call_id="call-1",
                )
            }
        else:
            yield "Only "
            yield "us."

    return lambda: build_chat_agent(FunctionModel(stream_function=stream))


async def _thread_with_question(db: AppDatabase) -> dict[str, Any]:
    tenant_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, 't', $2)",
        tenant_id,
        f"t-{tenant_id.hex[:12]}",
    )
    user_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, 'Maya')",
        user_id,
        f"{user_id.hex[:12]}@example.com",
    )
    issue_id = uuid.uuid4()
    datasource_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO issues (id, tenant_id, number, title, context) VALUES ($1, $2, 1, $3, $4)",
        issue_id,
        tenant_id,
        "Orders dropped",
        json.dumps({"datasource_id": str(datasource_id)}),
    )
    threads = IssueThreadRepository(db)
    thread = await threads.ensure_shared_thread(issue_id)
    await threads.append_message(
        thread["id"], author_kind="user", kind="comment", author_user_id=user_id, body_md="earlier"
    )
    question = await threads.append_message(
        thread["id"],
        author_kind="user",
        kind="comment",
        author_user_id=user_id,
        body_md="is it every region?",
        asks_agent=True,
    )
    return {
        "message_id": str(question["id"]),
        "kind": "answer",
        "thread_id": str(thread["id"]),
        "tenant_id": str(tenant_id),
        "issue_id": str(issue_id),
        "requested_by": str(user_id),
        "datasource_id": datasource_id,
    }


@pytest.fixture(autouse=True)
def _no_model_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)


async def test_turn_answers_with_a_snapshotted_query(migrated_db: AppDatabase) -> None:
    """The reply ends complete, with the query recorded and its snapshot stored."""
    request = await _thread_with_question(migrated_db)
    queries = FakeQueries()
    activity_fn = make_run_agent_turn_activity(migrated_db, _agent_factory(), queries)

    result = await ActivityEnvironment().run(activity_fn, request)

    assert result["status"] == "complete"
    reply = await IssueThreadRepository(migrated_db).get_reply_for_request(
        uuid.UUID(request["message_id"])
    )
    assert reply is not None
    assert (reply["status"], reply["body_md"]) == ("complete", "Only us.")
    assert reply["requested_by_user_id"] == uuid.UUID(request["requested_by"])
    (call,) = reply["payload"]["tool_calls"]
    assert call["tool"] == "run_query"
    snapshot = await migrated_db.fetch_one(
        "SELECT message_id, datasource_id, row_count FROM agent_query_results WHERE id = $1",
        uuid.UUID(call["query_result_id"]),
    )
    assert snapshot is not None
    assert snapshot["message_id"] == reply["id"]
    assert snapshot["datasource_id"] == request["datasource_id"]
    # The query ran as the person who asked
    assert queries.principals[0].user_id == uuid.UUID(request["requested_by"])


async def test_a_retried_turn_reuses_its_reply(migrated_db: AppDatabase) -> None:
    """Running the same request twice leaves one reply."""
    request = await _thread_with_question(migrated_db)
    activity_fn = make_run_agent_turn_activity(migrated_db, _agent_factory(), FakeQueries())

    await ActivityEnvironment().run(activity_fn, request)
    await ActivityEnvironment().run(activity_fn, request)

    rows = await migrated_db.fetch_all(
        "SELECT id FROM issue_thread_messages WHERE request_message_id = $1",
        uuid.UUID(request["message_id"]),
    )
    assert len(rows) == 1


async def test_a_cancelled_reply_is_not_answered(migrated_db: AppDatabase) -> None:
    """A reply cancelled while queued is skipped."""
    request = await _thread_with_question(migrated_db)
    threads = IssueThreadRepository(migrated_db)
    await threads.append_message(
        uuid.UUID(request["thread_id"]),
        author_kind="agent",
        kind="agent_reply",
        request_message_id=uuid.UUID(request["message_id"]),
        requested_by_user_id=uuid.UUID(request["requested_by"]),
        status="cancelled",
    )
    activity_fn = make_run_agent_turn_activity(migrated_db, _agent_factory(), FakeQueries())

    result = await ActivityEnvironment().run(activity_fn, request)

    assert result == {"status": "cancelled"}


async def test_failed_turn_is_marked_error(migrated_db: AppDatabase) -> None:
    """mark_turn_failed records the error on the queued reply."""
    request = await _thread_with_question(migrated_db)
    threads = IssueThreadRepository(migrated_db)
    await threads.append_message(
        uuid.UUID(request["thread_id"]),
        author_kind="agent",
        kind="agent_reply",
        request_message_id=uuid.UUID(request["message_id"]),
        status="streaming",
    )

    await ActivityEnvironment().run(
        make_mark_turn_failed_activity(migrated_db), {**request, "error": "model unavailable"}
    )

    reply = await threads.get_reply_for_request(uuid.UUID(request["message_id"]))
    assert reply is not None
    assert reply["status"] == "error"
    assert reply["payload"]["error"] == "model unavailable"


async def test_brief_draft_fills_the_brief_message(migrated_db: AppDatabase) -> None:
    """The draft lands in the brief message with citations resolved to messages."""
    from pydantic_ai.messages import ModelResponse, TextPart

    from dataing.agents.chat import build_brief_agent
    from dataing.temporal.activities.agent_turn import make_run_brief_draft_activity

    request = await _thread_with_question(migrated_db)
    threads = IssueThreadRepository(migrated_db)
    thread_id = uuid.UUID(request["thread_id"])
    question = await threads.get_message(uuid.UUID(request["message_id"]))
    assert question is not None
    brief_msg = await threads.append_message(
        thread_id,
        author_kind="agent",
        kind="brief",
        requested_by_user_id=uuid.UUID(request["requested_by"]),
        status="queued",
    )

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                TextPart(
                    json.dumps(
                        {
                            "symptom": "Orders dropped",
                            "findings": [
                                {"statement": "Asked about regions", "source_seq": question["seq"]}
                            ],
                        }
                    ),
                )
            ]
        )

    activity_fn = make_run_brief_draft_activity(
        migrated_db, lambda: build_brief_agent(FunctionModel(respond)), FakeQueries()
    )
    result = await ActivityEnvironment().run(
        activity_fn, {**request, "message_id": str(brief_msg["id"]), "kind": "draft_brief"}
    )

    assert result["status"] == "complete"
    stored = await threads.get_message(brief_msg["id"])
    assert stored is not None
    assert stored["status"] == "complete"
    brief = stored["payload"]["brief"]
    assert brief["symptom"] == "Orders dropped"
    assert brief["findings"][0]["message_id"] == str(question["id"])
    assert brief["scope"]["datasource_id"] == str(request["datasource_id"])
    assert stored["body_md"].startswith("**Investigation brief**")


async def _reply_with_snapshot(
    db: AppDatabase, threads: IssueThreadRepository, thread_id: uuid.UUID, tenant_id: str
) -> tuple[dict[str, Any], uuid.UUID]:
    reply = await threads.append_message(
        thread_id, author_kind="agent", kind="agent_reply", body_md="counted rows"
    )
    row = await db.execute_returning(
        """
        INSERT INTO agent_query_results (tenant_id, message_id, tool_call_id, sql, dialect)
        VALUES ($1, $2, 'call-1', 'SELECT 1', 'postgres')
        RETURNING id
        """,
        uuid.UUID(tenant_id),
        reply["id"],
    )
    assert row is not None
    result_id: uuid.UUID = row["id"]
    return reply, result_id


async def test_brief_draft_from_a_scratch_chat_reads_both_threads(
    migrated_db: AppDatabase,
) -> None:
    """Shared messages come first as #n, scratch ones as #sn; both kinds of citation resolve."""
    from pydantic_ai.messages import ModelResponse, TextPart

    from dataing.agents.chat import build_brief_agent
    from dataing.temporal.activities.agent_turn import make_run_brief_draft_activity

    request = await _thread_with_question(migrated_db)
    threads = IssueThreadRepository(migrated_db)
    user_id = uuid.UUID(request["requested_by"])
    question = await threads.get_message(uuid.UUID(request["message_id"]))
    assert question is not None
    _, shared_result = await _reply_with_snapshot(
        migrated_db, threads, uuid.UUID(request["thread_id"]), request["tenant_id"]
    )
    scratch = await threads.create_scratch_thread(
        uuid.UUID(request["tenant_id"]), uuid.UUID(request["issue_id"]), user_id, "enums"
    )
    scratch_note = await threads.append_message(
        scratch["id"],
        author_kind="user",
        kind="comment",
        author_user_id=user_id,
        body_md="app_v2 is a new enum value",
    )
    scratch_reply, scratch_result = await _reply_with_snapshot(
        migrated_db, threads, scratch["id"], request["tenant_id"]
    )
    brief_msg = await threads.append_message(
        scratch["id"],
        author_kind="agent",
        kind="brief",
        requested_by_user_id=user_id,
        status="queued",
    )
    seen: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for message in messages:
            seen.extend(str(getattr(part, "content", "")) for part in message.parts)
        return ModelResponse(
            parts=[
                TextPart(
                    json.dumps(
                        {
                            "symptom": "Orders dropped",
                            "findings": [
                                {
                                    "statement": "Asked about regions",
                                    "source_seq": question["seq"],
                                    "query_result_id": str(shared_result),
                                },
                                {
                                    "statement": "New enum value",
                                    "source_seq": f"s{scratch_note['seq']}",
                                    "query_result_id": str(scratch_result),
                                },
                            ],
                            "ruled_out": [
                                {"statement": "Counted", "source_seq": f"#s{scratch_reply['seq']}"}
                            ],
                        }
                    ),
                )
            ]
        )

    activity_fn = make_run_brief_draft_activity(
        migrated_db, lambda: build_brief_agent(FunctionModel(respond)), FakeQueries()
    )
    result = await ActivityEnvironment().run(
        activity_fn,
        {
            **request,
            "message_id": str(brief_msg["id"]),
            "thread_id": str(scratch["id"]),
            "kind": "draft_brief",
        },
    )

    assert result["status"] == "complete"
    history = "\n".join(seen)
    assert "earlier" in history
    assert f"#s{scratch_note['seq']} Maya: app_v2 is a new enum value" in history
    assert history.index("is it every region?") < history.index("app_v2 is a new enum value")
    stored = await threads.get_message(brief_msg["id"])
    assert stored is not None
    assert stored["thread_id"] == scratch["id"]
    brief = stored["payload"]["brief"]
    shared_claim, scratch_claim = brief["findings"]
    assert shared_claim["message_id"] == str(question["id"])
    assert shared_claim["query_result_id"] == str(shared_result)
    assert scratch_claim["message_id"] == str(scratch_note["id"])
    assert scratch_claim["query_result_id"] == str(scratch_result)
    assert brief["ruled_out"][0]["message_id"] == str(scratch_reply["id"])


INVALID_KEY = (
    "Anthropic rejected the API key (401). Set a valid ANTHROPIC_API_KEY and "
    "restart the API and the worker."
)


async def test_a_rejected_key_fails_the_turn_with_what_to_fix(migrated_db: AppDatabase) -> None:
    """The reply shows what to fix, not the raw ModelHTTPError, and isn't retried."""
    from pydantic_ai.exceptions import ModelHTTPError
    from temporalio.exceptions import ApplicationError

    from dataing.agents.chat import build_chat_agent

    async def reject(messages: list[ModelMessage], info: AgentInfo) -> Any:
        raise ModelHTTPError(status_code=401, model_name="claude-opus-5-5", body=None)
        yield  # an async generator, as stream functions are

    request = await _thread_with_question(migrated_db)
    activity_fn = make_run_agent_turn_activity(
        migrated_db, lambda: build_chat_agent(FunctionModel(stream_function=reject)), FakeQueries()
    )

    with pytest.raises(ApplicationError) as caught:
        await ActivityEnvironment().run(activity_fn, request)

    assert (caught.value.type, caught.value.non_retryable) == ("LLMRejected", True)
    assert caught.value.message == INVALID_KEY


async def test_a_rejected_key_fails_the_brief_draft_with_what_to_fix(
    migrated_db: AppDatabase,
) -> None:
    """Drafting a brief fails the same way: the reason, once."""
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.messages import ModelResponse
    from temporalio.exceptions import ApplicationError

    from dataing.agents.chat import build_brief_agent
    from dataing.temporal.activities.agent_turn import make_run_brief_draft_activity

    def reject(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=401, model_name="claude-opus-5-5", body=None)

    request = await _thread_with_question(migrated_db)
    brief_msg = await IssueThreadRepository(migrated_db).append_message(
        uuid.UUID(request["thread_id"]),
        author_kind="agent",
        kind="brief",
        requested_by_user_id=uuid.UUID(request["requested_by"]),
        status="queued",
    )
    activity_fn = make_run_brief_draft_activity(
        migrated_db, lambda: build_brief_agent(FunctionModel(reject)), FakeQueries()
    )

    with pytest.raises(ApplicationError) as caught:
        await ActivityEnvironment().run(
            activity_fn, {**request, "message_id": str(brief_msg["id"]), "kind": "draft_brief"}
        )

    assert (caught.value.type, caught.value.message) == ("LLMRejected", INVALID_KEY)
