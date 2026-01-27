"""Rich output formatting helpers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    pass

console = Console()


def format_event(event: Any) -> Panel:
    """Format a streaming event for display.

    Args:
        event: A StreamEvent from the SDK or dict with event data.

    Returns:
        A Rich Panel with formatted event content.
    """
    # Handle both object and dict access patterns
    event_type = getattr(event, "type", None) or (
        event.get("type") if isinstance(event, dict) else "unknown"
    )

    if event_type == "evidence":
        hypothesis = getattr(event, "hypothesis", None) or (
            event.get("hypothesis") if isinstance(event, dict) else "Unknown"
        )
        query = getattr(event, "query", None) or (
            event.get("query") if isinstance(event, dict) else ""
        )
        interpretation = getattr(event, "interpretation", None) or (
            event.get("interpretation") if isinstance(event, dict) else ""
        )
        supports = getattr(event, "supports_hypothesis", None)
        if supports is None and isinstance(event, dict):
            supports = event.get("supports_hypothesis")

        icon = "+" if supports else "-" if supports is False else "?"
        color = "green" if supports else "red" if supports is False else "yellow"

        # Build renderables list for Group
        renderables: list[Any] = [Text(f"{hypothesis}\n", style="bold")]

        if query:
            renderables.append(Text("Query:", style="dim"))
            renderables.append(Syntax(str(query), "sql", theme="monokai", line_numbers=False))
            renderables.append(Text(""))

        if interpretation:
            renderables.append(Text(f"Finding: {interpretation}", style="dim"))

        return Panel(
            Group(*renderables),
            title=f"[{color}]{icon}[/{color}] Evidence",
            border_style=color,
        )

    if event_type == "progress":
        message = getattr(event, "message", None) or (
            event.get("message") if isinstance(event, dict) else "Processing..."
        )
        return Panel(
            f"[yellow]...[/yellow] {escape(str(message))}",
            title="Progress",
            border_style="blue",
        )

    # Default: just show raw data
    return Panel(str(event), title=str(event_type))


def format_completion(event: Any) -> Panel:
    """Format completion event as a Rich Panel.

    Args:
        event: A completion event from the SDK or dict with result data.

    Returns:
        A Rich Panel with completion summary.
    """
    root_cause = getattr(event, "root_cause", None) or (
        event.get("root_cause") if isinstance(event, dict) else None
    )
    confidence = getattr(event, "confidence", None) or (
        event.get("confidence") if isinstance(event, dict) else 0
    )

    root_cause = root_cause or "No root cause identified"

    return Panel(
        f"[green]+[/green] Investigation complete\n\n"
        f"[bold]Root Cause:[/bold] {escape(str(root_cause))}\n"
        f"[bold]Confidence:[/bold] {confidence:.0%}",
        title="Result",
        border_style="green",
    )


def format_timestamp(start_time: float) -> str:
    """Format elapsed time since start as [MM:SS] string.

    Args:
        start_time: Unix timestamp of when the operation started.

    Returns:
        Elapsed time formatted as "[MM:SS]".
    """
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return f"[{minutes:02d}:{seconds:02d}]"


def format_hypothesis(event: Any, index: int, elapsed: str) -> Panel:
    """Format a hypothesis event as a blue-bordered panel.

    Args:
        event: A hypothesis event from the SDK or dict with event data.
        index: The hypothesis number (1-based).
        elapsed: Elapsed time string from format_timestamp.

    Returns:
        A Rich Panel with blue border showing the hypothesis.
    """
    # Extract hypothesis text from event data
    data = getattr(event, "data", None) or (event.get("data") if isinstance(event, dict) else {})
    if isinstance(data, dict):
        hypothesis_text = (
            data.get("hypothesis", "") or data.get("hypothesis_text", "") or data.get("message", "")
        )
    else:
        hypothesis_text = (
            getattr(data, "hypothesis", "")
            or getattr(data, "hypothesis_text", "")
            or getattr(data, "message", "")
        )

    hypothesis_text = hypothesis_text or "Testing hypothesis..."

    return Panel(
        escape(str(hypothesis_text)),
        title=f"{elapsed} Hypothesis #{index}",
        border_style="blue",
    )


def format_query(event: Any, elapsed: str) -> Panel:
    """Format a query execution event as a yellow-bordered panel with SQL highlighting.

    Args:
        event: A query event from the SDK or dict with event data.
        elapsed: Elapsed time string from format_timestamp.

    Returns:
        A Rich Panel with yellow border and syntax-highlighted SQL.
    """
    # Extract query from event data
    data = getattr(event, "data", None) or (event.get("data") if isinstance(event, dict) else {})
    if isinstance(data, dict):
        query = data.get("query", "") or data.get("sql", "")
    else:
        query = getattr(data, "query", "") or getattr(data, "sql", "")

    query = str(query) if query else "-- No query available"

    # Truncate long SQL (>20 lines)
    lines = query.split("\n")
    if len(lines) > 20:
        query = "\n".join(lines[:20]) + "\n-- ... (truncated)"

    return Panel(
        Syntax(query, "sql", theme="monokai", line_numbers=False),
        title=f"{elapsed} Executing Query",
        border_style="yellow",
    )


def format_evidence_item(event: Any, elapsed: str) -> Panel:
    """Format an evidence event as a green (supports) or red (refutes) panel.

    Args:
        event: An evidence event from the SDK or dict with event data.
        elapsed: Elapsed time string from format_timestamp.

    Returns:
        A Rich Panel with green or red border based on support verdict.
    """
    # Extract evidence data
    data = getattr(event, "data", None) or (event.get("data") if isinstance(event, dict) else {})
    if isinstance(data, dict):
        supports = data.get("supports_hypothesis", data.get("supports"))
        interpretation = data.get("interpretation", "") or data.get("finding", "")
        confidence = data.get("confidence", 0)
        query = data.get("query", "") or data.get("sql", "")
    else:
        supports = getattr(data, "supports_hypothesis", None) or getattr(data, "supports", None)
        interpretation = getattr(data, "interpretation", "") or getattr(data, "finding", "")
        confidence = getattr(data, "confidence", 0) or 0
        query = getattr(data, "query", "") or getattr(data, "sql", "")

    # Determine color and title based on support
    if supports is True:
        color = "green"
        verdict = "Supports"
    elif supports is False:
        color = "red"
        verdict = "Refutes"
    else:
        color = "yellow"
        verdict = "Inconclusive"

    # Build content
    renderables: list[Any] = []

    if interpretation:
        renderables.append(Text(str(interpretation), style=""))

    if confidence:
        conf_pct = confidence * 100 if confidence <= 1 else confidence
        renderables.append(Text(f"\nConfidence: {conf_pct:.0f}%", style="dim"))

    if query:
        query_str = str(query)
        # Truncate long SQL
        lines = query_str.split("\n")
        if len(lines) > 10:
            query_str = "\n".join(lines[:10]) + "\n-- ... (truncated)"
        renderables.append(Text("\nQuery:", style="dim"))
        renderables.append(Syntax(query_str, "sql", theme="monokai", line_numbers=False))

    if not renderables:
        renderables.append(Text("Evidence collected", style="dim"))

    return Panel(
        Group(*renderables),
        title=f"{elapsed} Evidence: {verdict}",
        border_style=color,
    )


def format_synthesis(event: Any, elapsed: str) -> Panel:
    """Format a synthesis/completion event as a cyan-bordered panel.

    Args:
        event: A completion event from the SDK or dict with result data.
        elapsed: Elapsed time string from format_timestamp.

    Returns:
        A Rich Panel with cyan border showing root cause and recommendations.
    """
    # Extract synthesis data
    data = getattr(event, "data", None) or (event.get("data") if isinstance(event, dict) else {})
    if isinstance(data, dict):
        root_cause = data.get("root_cause", "")
        confidence = data.get("confidence", 0)
        recommendations = data.get("recommendations", [])
    else:
        root_cause = getattr(data, "root_cause", "") or ""
        confidence = getattr(data, "confidence", 0) or 0
        recommendations = getattr(data, "recommendations", []) or []

    # Also check event-level attributes for completion events
    if not root_cause:
        root_cause = getattr(event, "root_cause", None) or (
            event.get("root_cause") if isinstance(event, dict) else ""
        )
    if not confidence:
        confidence = getattr(event, "confidence", None) or (
            event.get("confidence") if isinstance(event, dict) else 0
        )

    root_cause = root_cause or "No root cause identified"
    conf_pct = confidence * 100 if confidence and confidence <= 1 else (confidence or 0)

    # Build content
    renderables: list[Any] = [
        Text("Root Cause:", style="bold"),
        Text(f"  {escape(str(root_cause))}\n"),
        Text(f"Confidence: {conf_pct:.0f}%\n", style="dim"),
    ]

    if recommendations:
        renderables.append(Text("Recommendations:", style="bold"))
        rec_table = Table(show_header=False, box=None, padding=(0, 0, 0, 2))
        rec_table.add_column("bullet", style="cyan", width=2)
        rec_table.add_column("text")
        for rec in recommendations[:5]:  # Limit to 5 recommendations
            rec_text = str(rec.get("text", rec) if isinstance(rec, dict) else rec)
            rec_table.add_row("*", rec_text)
        renderables.append(rec_table)

    return Panel(
        Group(*renderables),
        title=f"{elapsed} Synthesis",
        border_style="cyan",
    )


def print_status(
    config: dict[str, Any],
    api_key: str | None,
    connected: bool,
    error: str | None = None,
) -> None:
    """Print connection status panel.

    Args:
        config: Configuration dict with api_url and default_datasource_name.
        api_key: The API key (will be masked in output).
        connected: Whether the connection test succeeded.
        error: Optional error message if connection failed.
    """
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("Backend", config.get("api_url", "Not configured"))
    table.add_row(
        "API Key", f"***{api_key[-4:]}" if api_key and len(api_key) >= 4 else "Not configured"
    )
    table.add_row("Default DS", config.get("default_datasource_name", "None"))

    status = "[green]* Connected[/green]" if connected else "[red]* Disconnected[/red]"
    if error:
        status += f"\n  [dim]{escape(error)}[/dim]"
    table.add_row("Status", status)

    console.print(Panel(table, title="dataing CLI"))


def print_datasources_table(datasources: list[Any]) -> None:
    """Print datasources in table format.

    Args:
        datasources: List of datasource objects or dicts.
    """
    table = Table(title="Datasources")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Status")

    for ds in datasources:
        ds_id = getattr(ds, "id", None) or (ds.get("id") if isinstance(ds, dict) else "")
        ds_name = getattr(ds, "name", None) or (ds.get("name") if isinstance(ds, dict) else "")
        ds_type = getattr(ds, "source_type", None) or (
            ds.get("source_type") if isinstance(ds, dict) else ""
        )
        ds_status = getattr(ds, "status", None) or (
            ds.get("status") if isinstance(ds, dict) else ""
        )

        status_icon = "[green]*[/green]" if ds_status == "connected" else "[red]*[/red]"
        id_display = f"{ds_id[:12]}..." if len(str(ds_id)) > 12 else ds_id
        table.add_row(id_display, ds_name, ds_type, status_icon)

    console.print(table)


def print_runs_table(runs: list[Any]) -> None:
    """Print investigation runs in table format.

    Args:
        runs: List of run objects or dicts.
    """
    table = Table(title="Recent Runs")
    table.add_column("ID", style="cyan")
    table.add_column("Status")
    table.add_column("Goal")
    table.add_column("Created")

    status_styles = {
        "running": "yellow",
        "completed": "green",
        "failed": "red",
    }

    for run in runs:
        run_id = getattr(run, "run_id", None) or (
            run.get("run_id") if isinstance(run, dict) else ""
        )
        status = getattr(run, "status", None) or (
            run.get("status") if isinstance(run, dict) else ""
        )
        goal = getattr(run, "goal", None) or (run.get("goal") if isinstance(run, dict) else "")
        created = getattr(run, "created_at", None) or (
            run.get("created_at") if isinstance(run, dict) else ""
        )

        style = status_styles.get(str(status), "white")
        id_display = f"{run_id[:12]}..." if len(str(run_id)) > 12 else run_id
        goal_display = f"{goal[:40]}..." if len(str(goal)) > 40 else goal
        created_display = str(created)[:19] if created else ""

        table.add_row(
            id_display,
            f"[{style}]{status}[/]",
            goal_display,
            created_display,
        )

    console.print(table)
