"""MCP (Model Context Protocol) server for dataing.

This module provides MCP tools that can be used by Claude
and other MCP-compatible clients to interact with dataing.

Tools provided:
- investigate_anomaly: Start a full investigation
- query_dataset: Execute a read-only SQL query
- get_table_schema: Get schema for a specific table
"""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from dataing.adapters.context.engine import DefaultContextEngine
from dataing.adapters.db.postgres import PostgresAdapter
from dataing.adapters.llm.client import AnthropicClient
from dataing.core.domain_types import AnomalyAlert
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.core.state import InvestigationState
from dataing.safety.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from dataing.safety.validator import validate_query


def create_server(
    db: PostgresAdapter,
    llm: AnthropicClient,
) -> Server:
    """Create and configure the MCP server.

    Args:
        db: Database adapter for queries.
        llm: LLM client for investigations.

    Returns:
        Configured MCP Server.
    """
    server = Server("dataing")

    context_engine = DefaultContextEngine(db=db)
    circuit_breaker = CircuitBreaker(CircuitBreakerConfig())

    orchestrator = InvestigationOrchestrator(
        db=db,
        llm=llm,
        context_engine=context_engine,
        circuit_breaker=circuit_breaker,
        config=OrchestratorConfig(),
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available MCP tools."""
        return [
            Tool(
                name="investigate_anomaly",
                description="Investigate a data quality anomaly to find the root cause",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dataset_id": {
                            "type": "string",
                            "description": "The affected table (e.g., 'schema.table_name')",
                        },
                        "metric_name": {
                            "type": "string",
                            "description": "The metric that deviated (e.g., 'row_count')",
                        },
                        "expected_value": {
                            "type": "number",
                            "description": "Expected metric value",
                        },
                        "actual_value": {
                            "type": "number",
                            "description": "Actual metric value",
                        },
                        "deviation_pct": {
                            "type": "number",
                            "description": "Percentage deviation",
                        },
                        "anomaly_date": {
                            "type": "string",
                            "description": "Date of the anomaly (YYYY-MM-DD)",
                        },
                    },
                    "required": [
                        "dataset_id",
                        "metric_name",
                        "expected_value",
                        "actual_value",
                        "deviation_pct",
                        "anomaly_date",
                    ],
                },
            ),
            Tool(
                name="query_dataset",
                description="Execute a read-only SQL query against the data warehouse",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "SELECT query to execute (must include LIMIT)",
                        },
                    },
                    "required": ["sql"],
                },
            ),
            Tool(
                name="get_table_schema",
                description="Get schema information for a table",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Fully qualified table name (schema.table)",
                        },
                    },
                    "required": ["table_name"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        if name == "investigate_anomaly":
            return await _investigate_anomaly(orchestrator, arguments)
        elif name == "query_dataset":
            return await _query_dataset(db, arguments)
        elif name == "get_table_schema":
            return await _get_table_schema(db, arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server


async def _investigate_anomaly(
    orchestrator: InvestigationOrchestrator,
    args: dict[str, Any],
) -> list[TextContent]:
    """Execute investigation and return findings.

    Args:
        orchestrator: Investigation orchestrator.
        args: Tool arguments.

    Returns:
        List of TextContent with findings.
    """
    alert = AnomalyAlert(
        dataset_id=args["dataset_id"],
        metric_name=args["metric_name"],
        expected_value=args["expected_value"],
        actual_value=args["actual_value"],
        deviation_pct=args["deviation_pct"],
        anomaly_date=args["anomaly_date"],
        severity="medium",
    )

    state = InvestigationState(id=str(uuid.uuid4()), alert=alert)

    try:
        finding = await orchestrator.run_investigation(state)

        result = f"""Investigation Complete
=====================

**Status:** {finding.status}
**Root Cause:** {finding.root_cause or 'Not determined'}
**Confidence:** {finding.confidence:.0%}
**Duration:** {finding.duration_seconds:.1f}s

**Evidence:**
"""
        for ev in finding.evidence:
            result += f"\n- {ev.interpretation} (confidence: {ev.confidence:.0%})"

        result += "\n\n**Recommendations:**\n"
        for rec in finding.recommendations:
            result += f"- {rec}\n"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(type="text", text=f"Investigation failed: {e}")]


async def _query_dataset(
    db: PostgresAdapter,
    args: dict[str, Any],
) -> list[TextContent]:
    """Execute a read-only query.

    Args:
        db: Database adapter.
        args: Tool arguments.

    Returns:
        List of TextContent with query results.
    """
    sql = args["sql"]

    try:
        # Validate query for safety
        validate_query(sql)

        result = await db.execute_query(sql)

        # Format results
        if not result.rows:
            return [TextContent(type="text", text="Query returned no results.")]

        lines = [f"Columns: {', '.join(result.columns)}"]
        lines.append(f"Row count: {result.row_count}")
        lines.append("")

        for row in result.rows[:100]:
            row_str = " | ".join(str(v) for v in row.values())
            lines.append(row_str)

        if result.row_count > 100:
            lines.append(f"... and {result.row_count - 100} more rows")

        return [TextContent(type="text", text="\n".join(lines))]

    except Exception as e:
        return [TextContent(type="text", text=f"Query failed: {e}")]


async def _get_table_schema(
    db: PostgresAdapter,
    args: dict[str, Any],
) -> list[TextContent]:
    """Get schema for a table.

    Args:
        db: Database adapter.
        args: Tool arguments.

    Returns:
        List of TextContent with schema information.
    """
    table_name = args["table_name"]

    try:
        schema = await db.get_schema(table_pattern=table_name)
        table = schema.get_table(table_name)

        if not table:
            return [TextContent(type="text", text=f"Table not found: {table_name}")]

        lines = [f"Table: {table.table_name}", ""]
        lines.append("Columns:")
        for col in table.columns:
            col_type = table.column_types.get(col, "unknown")
            lines.append(f"  - {col}: {col_type}")

        return [TextContent(type="text", text="\n".join(lines))]

    except Exception as e:
        return [TextContent(type="text", text=f"Schema lookup failed: {e}")]


async def run_server(database_url: str, anthropic_api_key: str) -> None:
    """Run the MCP server.

    Args:
        database_url: PostgreSQL connection URL.
        anthropic_api_key: Anthropic API key.
    """
    db = PostgresAdapter(database_url)
    await db.connect()

    llm = AnthropicClient(api_key=anthropic_api_key)

    server = create_server(db, llm)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

    await db.close()
