"""Read-only tools of the issue chat agent (docs/specs/0001_issue_chat.md §7.5).

No tool writes to the issue or an investigation. run_query stores a snapshot of
what the agent saw, and propose_steer only records a proposal for a person to send.
Failures reach the model as structured results; invalid SQL is returned as a retry
prompt so the model can correct it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.tools import Tool

from dataing.agents.chat.deps import ChatDeps, ToolCallRecord
from dataing.core.agent_query import AgentQueryError, AgentQueryErrorCode

SteerKind = Literal["add_context", "rule_out", "add_hypothesis", "stop_and_synthesize"]


def _record(
    ctx: RunContext[ChatDeps],
    tool: str,
    args: dict[str, Any],
    summary: str,
    *,
    error: AgentQueryError | None = None,
    query_result_id: Any = None,
    duration_ms: int | None = None,
    row_count: int | None = None,
) -> None:
    ctx.deps.tool_calls.append(
        ToolCallRecord(
            id=ctx.tool_call_id or f"{tool}-{len(ctx.deps.tool_calls)}",
            tool=tool,
            input=args,
            status="error" if error else "ok",
            summary=summary,
            query_result_id=query_result_id,
            error_code=error.code.value if error else None,
            duration_ms=duration_ms,
            row_count=row_count,
        )
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


async def get_issue_context(ctx: RunContext[ChatDeps]) -> dict[str, Any]:
    """Return the issue, its context, recent events and linked investigation runs."""
    result = await ctx.deps.services.issue_context()
    _record(ctx, "get_issue_context", {}, "read the issue")
    return result


async def list_tables(ctx: RunContext[ChatDeps], pattern: str | None = None) -> dict[str, Any]:
    """List tables in the issue's datasource that the asker can see.

    Args:
        ctx: Run context.
        pattern: Optional substring or glob to filter table names.
    """
    args = {"pattern": pattern}
    try:
        result = await ctx.deps.services.list_tables(pattern)
    except AgentQueryError as e:
        _record(ctx, "list_tables", args, e.message, error=e)
        return e.to_dict()
    _record(ctx, "list_tables", args, _plural(len(result.get("tables", [])), "table"))
    return result


async def describe_table(ctx: RunContext[ChatDeps], table: str) -> dict[str, Any]:
    """Describe one table's columns and types.

    Args:
        ctx: Run context.
        table: Table name, schema.table or catalog.schema.table.
    """
    args = {"table": table}
    try:
        result = await ctx.deps.services.describe_table(table)
    except AgentQueryError as e:
        _record(ctx, "describe_table", args, e.message, error=e)
        return e.to_dict()
    _record(ctx, "describe_table", args, _plural(len(result.get("columns", [])), "column"))
    return result


async def run_query(ctx: RunContext[ChatDeps], sql: str, purpose: str) -> dict[str, Any]:
    """Run one read-only SELECT as the person who asked and return a summary of rows.

    Args:
        ctx: Run context.
        sql: A single SELECT statement in the datasource's SQL dialect.
        purpose: One short sentence saying what the query checks.
    """
    args = {"sql": sql, "purpose": purpose}
    services = ctx.deps.services
    call_id = ctx.tool_call_id or f"run_query-{len(ctx.deps.tool_calls)}"
    try:
        result = await services.run_query(sql, purpose)
    except AgentQueryError as e:
        snapshot_id = await services.save_query_result(call_id, sql, None, e.message)
        _record(ctx, "run_query", args, e.message, error=e, query_result_id=snapshot_id)
        if e.code == AgentQueryErrorCode.VALIDATION_FAILED:
            raise ModelRetry(f"The query was rejected: {e.message}. Fix it and try again.") from e
        return e.to_dict()
    snapshot_id = await services.save_query_result(call_id, result.sql, result, None)
    summary = _plural(result.row_count, "row") + (" (truncated)" if result.truncated else "")
    _record(
        ctx,
        "run_query",
        args,
        summary,
        query_result_id=snapshot_id,
        duration_ms=result.duration_ms,
        row_count=result.row_count,
    )
    view = result.model_view.to_dict()
    view["query_result_id"] = str(snapshot_id)
    view["sql"] = result.sql
    return view


async def get_investigation(ctx: RunContext[ChatDeps], run_id: str) -> dict[str, Any]:
    """Return a linked investigation's brief, outcome and steers.

    A finished run's outcome lists each hypothesis and how it ended. A running
    run has `live` instead: its current step and each hypothesis's id and status;
    use that id as propose_steer's hypothesis_id to rule one out.

    Args:
        ctx: Run context.
        run_id: The investigation id.
    """
    result = await ctx.deps.services.get_investigation(run_id)
    if result is None:
        _record(ctx, "get_investigation", {"run_id": run_id}, "not found")
        return {"error": "not_found", "message": f"No investigation {run_id} on this issue"}
    _record(ctx, "get_investigation", {"run_id": run_id}, "read the investigation")
    return result


async def propose_steer(
    ctx: RunContext[ChatDeps],
    run_id: str,
    kind: SteerKind,
    text: str,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Propose a steer for a running investigation. A person decides whether to send it.

    Args:
        ctx: Run context.
        run_id: The running investigation's id.
        kind: add_context, rule_out, add_hypothesis or stop_and_synthesize.
        text: The fact, reason or hypothesis, in one or two sentences.
        hypothesis_id: The hypothesis to rule out, for rule_out.
    """
    proposal = {"run_id": run_id, "kind": kind, "text": text, "hypothesis_id": hypothesis_id}
    ctx.deps.proposals.append(proposal)
    _record(ctx, "propose_steer", proposal, f"proposed {kind.replace('_', ' ')}")
    return {"proposed": True, "note": "Shown to the team with a Send button; nothing was sent."}


CHAT_TOOLS: list[Tool[ChatDeps]] = [
    Tool(get_issue_context),
    Tool(list_tables),
    Tool(describe_table),
    Tool(run_query),
    Tool(get_investigation),
    Tool(propose_steer),
]
