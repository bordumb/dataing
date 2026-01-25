"""Investigation run commands."""

from __future__ import annotations

import typer

app = typer.Typer()


@app.command("start")
def start_run() -> None:
    """Start a new investigation run."""
    typer.echo("Run start command (not yet implemented)")


@app.command("watch")
def watch_run() -> None:
    """Watch a running investigation."""
    typer.echo("Run watch command (not yet implemented)")
