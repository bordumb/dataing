"""Dependencies and results of an issue chat agent turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from dataing.adapters.datasource.gateway import UserPrincipal
from dataing.core.agent_query import AgentQueryResult


class ChatServices(Protocol):
    """What the chat agent's tools can reach. The turn activity implements it.

    Every method is read-only except save_query_result, which stores the snapshot
    of a query the agent already ran.
    """

    async def issue_context(self) -> dict[str, Any]:
        """Return the issue, its context, recent events and linked runs."""
        ...

    async def run_query(self, sql: str, purpose: str) -> AgentQueryResult:
        """Run a read-only query as the asker (raises AgentQueryError)."""
        ...

    async def save_query_result(
        self,
        tool_call_id: str,
        sql: str,
        result: AgentQueryResult | None,
        error: str | None,
    ) -> UUID:
        """Store what the agent saw and return the snapshot id."""
        ...

    async def list_tables(self, pattern: str | None) -> dict[str, Any]:
        """List tables the asker can see (raises AgentQueryError)."""
        ...

    async def describe_table(self, table: str) -> dict[str, Any]:
        """Describe one table's columns (raises AgentQueryError)."""
        ...

    async def get_investigation(self, run_id: str) -> dict[str, Any] | None:
        """Return a linked investigation's hypotheses, evidence and synthesis."""
        ...


@dataclass
class ToolCallRecord:
    """One tool call, as shown collapsed under the agent's reply."""

    id: str
    tool: str
    input: dict[str, Any]
    status: str  # "ok" or "error"
    summary: str
    query_result_id: UUID | None = None
    error_code: str | None = None
    # A query's totals, for the collapsed line ("Ran 1 query · 212 ms · 4 rows")
    duration_ms: int | None = None
    row_count: int | None = None

    def to_payload(self) -> dict[str, Any]:
        """Return the record as JSON-safe payload data."""
        return {
            "id": self.id,
            "tool": self.tool,
            "input": self.input,
            "status": self.status,
            "summary": self.summary,
            "query_result_id": str(self.query_result_id) if self.query_result_id else None,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "row_count": self.row_count,
        }


@dataclass
class ChatDeps:
    """Per-turn dependencies handed to every tool."""

    principal: UserPrincipal | None
    services: ChatServices
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TurnUsage:
    """Token usage of a turn, including prompt-cache reads."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def to_payload(self) -> dict[str, int]:
        """Return the usage as payload data."""
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass
class TurnResult:
    """What one agent turn produced."""

    text: str
    tool_calls: list[ToolCallRecord]
    proposals: list[dict[str, Any]]
    usage: TurnUsage
