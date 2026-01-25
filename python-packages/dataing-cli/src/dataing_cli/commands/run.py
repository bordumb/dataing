"""Investigation run commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel

from dataing_cli.config import get_client, load_config
from dataing_cli.display import format_completion, format_event
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

    console.print(f"[green]+[/green] Started run: [cyan]{run.run_id}[/cyan]")

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
    """Stream and display run events with Rich Live.

    Args:
        client: The DataingClient instance.
        run_id: The run ID to watch.
        state: The CLI state object.
    """
    console.print(f"\n[dim]Streaming events for run {run_id}...[/dim]\n")

    json_output = state.json_output if state else False

    if json_output:
        # JSON mode: print events as JSON lines
        for event in client.stream_run(run_id):
            console.print(json.dumps(event.model_dump(), indent=2, default=str))
            if event.is_terminal:
                if event.event == "run_failed":
                    raise typer.Exit(1)
                return
        return

    # Rich Live mode for interactive display
    with Live(
        Panel("Initializing...", title="Progress"),
        refresh_per_second=4,
        transient=True,
        console=console,
    ) as live:
        for event in client.stream_run(run_id):
            event_type = event.event

            if event_type in ("run_progress", "hypothesis_testing", "context_gathered"):
                # Progress events - transient display
                message = event.data.get("message", event_type.replace("_", " ").title())
                live.update(Panel(f"[yellow]...[/yellow] {message}", title="Progress"))

            elif event_type in ("run_evidence", "hypothesis_result"):
                # Evidence events - permanent display
                live.stop()
                console.print(format_event(event))
                live.start()

            elif event_type == "run_completed":
                live.stop()
                panel = format_completion(event.data)
                console.print(panel)
                return

            elif event_type == "run_failed":
                live.stop()
                error = event.data.get("error", "Unknown error")
                console.print(
                    Panel(
                        f"[red]-[/red] {error}",
                        title="Failed",
                        border_style="red",
                    )
                )
                raise typer.Exit(1)

            elif event_type == "run_started":
                live.update(Panel("[yellow]...[/yellow] Investigation started", title="Progress"))
