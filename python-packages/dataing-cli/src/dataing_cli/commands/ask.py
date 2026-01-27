"""Interactive investigation ask command."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel

from dataing_cli.config import (
    get_client,
    get_current_investigation_id,
    set_current_investigation_id,
)
from dataing_cli.display import (
    format_evidence_item,
    format_hypothesis,
    format_synthesis,
    format_timestamp,
)
from dataing_cli.errors import cli_error_handler

if TYPE_CHECKING:
    from dataing_sdk import DataingClient

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
@cli_error_handler
def ask(
    ctx: typer.Context,
    question: Annotated[
        str | None,
        typer.Argument(help="Question to ask (one-shot mode)"),
    ] = None,
    investigation: Annotated[
        str | None,
        typer.Option(
            "--investigation",
            "-i",
            help="Investigation ID to attach to",
        ),
    ] = None,
) -> None:
    """Ask questions about an investigation.

    With no args: enters interactive REPL mode.
    With question: sends one-shot question and streams response.

    Examples:
        # One-shot question mode
        dataing ask "What is the root cause?"

        # Attach to specific investigation and ask
        dataing ask --investigation abc123 "Can you investigate upstream?"

        # Enter interactive REPL mode
        dataing ask
    """
    state = ctx.obj

    # Resolve investigation ID: explicit flag > stored config
    inv_id = investigation or get_current_investigation_id()

    if not inv_id:
        console.print(
            "[red]No investigation attached.[/red]\n"
            "Use [bold]--investigation <id>[/bold] to specify one, "
            "or run [bold]dataing run start[/bold] first."
        )
        raise typer.Exit(1)

    # Get client
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    # Save as current investigation if explicitly provided
    if investigation:
        set_current_investigation_id(investigation)

    if question:
        # One-shot mode
        _send_one_shot(client, inv_id, question, state)
    else:
        # Interactive REPL mode (implemented in fn-31.4)
        _enter_repl(client, inv_id, state)


def _send_one_shot(
    client: DataingClient,
    investigation_id: str,
    question: str,
    state: Any,
) -> None:
    """Send a single question and stream the response.

    Args:
        client: The DataingClient instance.
        investigation_id: The investigation ID.
        question: The user question to send.
        state: The CLI state object.
    """
    is_tty = sys.stdout.isatty()

    console.print(f"\n[dim]Sending message to investigation {investigation_id[:8]}...[/dim]\n")

    # Send message to investigation
    client.send_message(investigation_id, question)

    # Stream response events
    panels: list[Any] = []
    start_time = time.time()
    hypothesis_idx = 0

    # Header showing the question
    panels.append(
        Panel(
            f"[bold]You:[/bold] {question}",
            border_style="dim",
        )
    )

    if not is_tty:
        # Plain text mode for non-TTY
        _stream_response_plain(client, investigation_id, start_time)
        return

    # TTY mode with Rich Live display
    with Live(
        Group(*panels),
        refresh_per_second=4,
        transient=False,
        console=console,
    ) as live:
        try:
            for event in client.stream_run(investigation_id):
                event_type = event.event
                elapsed = format_timestamp(start_time)

                if event_type == "hypothesis_testing":
                    hypothesis_idx += 1
                    panels.append(format_hypothesis(event, hypothesis_idx, elapsed))
                    live.update(Group(*panels))

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
                    # Just refresh display
                    live.refresh()

                elif event_type == "awaiting_user":
                    # Investigation is waiting for user input - we're done streaming
                    panels.append(
                        Panel(
                            "[dim]Investigation processed your message.[/dim]",
                            title=f"{elapsed} Ready",
                            border_style="green",
                        )
                    )
                    live.update(Group(*panels))
                    return

                # Check for terminal events
                if event.is_terminal:
                    return

        except KeyboardInterrupt:
            elapsed = format_timestamp(start_time)
            panels.append(
                Panel(
                    "[yellow]Interrupted[/yellow]",
                    title=f"{elapsed} Cancelled",
                    border_style="yellow",
                )
            )
            live.update(Group(*panels))
            raise typer.Exit(130) from None


def _stream_response_plain(
    client: DataingClient,
    investigation_id: str,
    start_time: float,
) -> None:
    """Stream response in plain text mode for non-TTY.

    Args:
        client: The DataingClient instance.
        investigation_id: The investigation ID.
        start_time: The start time for elapsed calculation.
    """
    for event in client.stream_run(investigation_id):
        event_type = event.event
        elapsed = format_timestamp(start_time)

        if event_type == "hypothesis_testing":
            hypothesis = event.data.get("hypothesis", "")
            print(f"{elapsed} Testing hypothesis: {hypothesis}")

        elif event_type in ("run_evidence", "hypothesis_result"):
            kind = event.data.get("kind", "unknown")
            print(f"{elapsed} Evidence: {kind}")

        elif event_type == "run_completed":
            root_cause = event.data.get("root_cause", "")
            print(f"{elapsed} Completed: {root_cause}")
            return

        elif event_type == "run_failed":
            error = event.data.get("error", "Unknown error")
            print(f"{elapsed} Failed: {error}")
            raise typer.Exit(1)

        elif event_type == "awaiting_user":
            print(f"{elapsed} Ready for input")
            return

        if event.is_terminal:
            return


def _enter_repl(client: DataingClient, investigation_id: str, state: Any) -> None:
    """Enter interactive REPL mode.

    Args:
        client: The DataingClient instance.
        investigation_id: The investigation ID.
        state: The CLI state object.
    """
    # Placeholder - full implementation in fn-31.4
    console.print(
        f"\n[bold]Entering interactive mode for investigation {investigation_id[:8]}...[/bold]\n"
        "[dim]REPL mode will be available in a future update.[/dim]\n"
        '[dim]For now, use: dataing ask "your question"[/dim]'
    )
    raise typer.Exit(0)
