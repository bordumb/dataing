"""Investigation run commands."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text  # Used for header panel

from dataing_cli.config import get_client, get_frontend_url, load_config
from dataing_cli.display import (
    format_evidence_item,
    format_hypothesis,
    format_query,
    format_synthesis,
    format_timestamp,
)
from dataing_cli.errors import cli_error_handler

if TYPE_CHECKING:
    from dataing_sdk import DataingClient

app = typer.Typer()
console = Console()


@app.command("start")
@cli_error_handler
def start_run(
    ctx: typer.Context,
    dataset: Annotated[str, typer.Argument(help="Dataset to investigate (e.g., 'schema.table')")],
    goal: Annotated[str, typer.Option("--goal", "-g", help="Investigation goal")],
    datasource: Annotated[
        str | None,
        typer.Option("--datasource", "-d", help="Datasource ID"),
    ] = None,
    no_watch: Annotated[
        bool,
        typer.Option("--no-watch", help="Don't stream progress"),
    ] = False,
) -> None:
    """Start a new investigation run."""
    from dataing_sdk import AssetRef

    state = ctx.obj
    config = load_config()

    ds_id = datasource or config.get("default_datasource_id")
    if not ds_id:
        console.print(
            "[red]Error:[/red] No datasource specified. "
            "Use --datasource or run 'dataing ds attach'"
        )
        raise typer.Exit(1)

    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    # Parse dataset into AssetRef
    # Try to infer platform from datasource, default to "unknown"
    asset = AssetRef(platform="unknown", name=dataset, datasource_id=ds_id)

    with console.status("[bold blue]Starting investigation..."):
        run = client.run(assets=[asset], goal=goal)

    frontend_url = get_frontend_url()
    inv_url = f"{frontend_url}/investigations/{run.run_id}"
    console.print(f"[green]+[/green] Started run: [cyan]{run.run_id}[/cyan]")
    console.print(f"[green]+[/green] View at: [link={inv_url}]{inv_url}[/link]")

    if state and state.json_output:
        console.print(json.dumps(run.model_dump(), indent=2, default=str))
        return

    if not no_watch:
        _watch_run(client, run.run_id, state)


@app.command("watch")
@cli_error_handler
def watch_run(
    ctx: typer.Context,
    run_id: Annotated[str, typer.Argument(help="Run ID to watch")],
) -> None:
    """Watch a running investigation."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )
    _watch_run(client, run_id, state)


def _watch_run(client: DataingClient, run_id: str, state: Any) -> None:
    """Stream and display run events with Rich Live timeline.

    Args:
        client: The DataingClient instance.
        run_id: The run ID to watch.
        state: The CLI state object.
    """
    console.print(f"\n[dim]Streaming events for run {run_id}...[/dim]\n")

    json_output = state.json_output if state else False

    if json_output:
        # JSON mode: print events as JSON lines (handled by fn-29.4)
        for event in client.stream_run(run_id):
            console.print(json.dumps(event.model_dump(), indent=2, default=str))
            if event.is_terminal:
                if event.event == "run_failed":
                    raise typer.Exit(1)
                return
        return

    # Timeline display mode - accumulate panels progressively
    panels: list[Any] = []
    start_time = time.time()
    hypothesis_idx = 0

    # Header panel with goal (will be updated)
    header = Text(f"Investigation: {run_id}", style="bold")
    panels.append(Panel(header, border_style="dim"))

    with Live(
        Group(*panels),
        refresh_per_second=4,
        transient=False,  # Keep timeline visible after completion
        console=console,
    ) as live:
        try:
            for event in client.stream_run(run_id):
                event_type = event.event
                elapsed = format_timestamp(start_time)

                if event_type == "run_started":
                    # Update header with goal
                    goal = event.data.get("goal", "")
                    if goal:
                        panels[0] = Panel(
                            Text(f"Goal: {goal}", style="bold"),
                            title=f"{elapsed} Investigation Started",
                            border_style="dim",
                        )
                    live.update(Group(*panels))

                elif event_type == "hypothesis_testing":
                    hypothesis_idx += 1
                    panels.append(format_hypothesis(event, hypothesis_idx, elapsed))
                    live.update(Group(*panels))

                elif event_type == "run_progress":
                    # Check if this is a query execution
                    data = event.data or {}
                    if data.get("query") or data.get("sql"):
                        panels.append(format_query(event, elapsed))
                        live.update(Group(*panels))
                    # Otherwise just update the live display without adding panel
                    # (subtle progress indicator)

                elif event_type in ("run_evidence", "hypothesis_result"):
                    panels.append(format_evidence_item(event, elapsed))
                    live.update(Group(*panels))

                elif event_type == "run_completed":
                    panels.append(format_synthesis(event, elapsed))
                    live.update(Group(*panels))
                    return

                elif event_type == "run_failed":
                    error = event.data.get("error", "Unknown error")
                    panels.append(
                        Panel(
                            f"[red]-[/red] {error}",
                            title=f"{elapsed} Failed",
                            border_style="red",
                        )
                    )
                    live.update(Group(*panels))
                    raise typer.Exit(1)

                elif event_type == "run_heartbeat":
                    # Heartbeat - just refresh display without adding new panel
                    # This keeps the connection alive visually
                    live.refresh()

                elif event_type == "context_gathered":
                    # Show context gathering progress
                    message = event.data.get("message", "Context gathered")
                    panels.append(
                        Panel(
                            f"[dim]{message}[/dim]",
                            title=f"{elapsed} Context",
                            border_style="dim",
                        )
                    )
                    live.update(Group(*panels))

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            elapsed = format_timestamp(start_time)
            panels.append(
                Panel(
                    "[yellow]Investigation interrupted by user[/yellow]",
                    title=f"{elapsed} Interrupted",
                    border_style="yellow",
                )
            )
            live.update(Group(*panels))
            raise typer.Exit(130) from None
