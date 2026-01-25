"""Rich output formatting helpers."""

from __future__ import annotations

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
