"""Dataing CLI - Autonomous Data Quality Investigation."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from dataing_cli.commands import ds, run

app = typer.Typer(
    name="dataing",
    help="Autonomous Data Quality Investigation CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,  # Security: don't leak API keys
)
console = Console()


class State:
    """Shared CLI state passed via typer.Context.obj."""

    def __init__(self) -> None:
        """Initialize state with defaults."""
        self.verbose: bool = False
        self.json_output: bool = False
        self.api_key: str | None = None
        self.base_url: str | None = None


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", "-V", help="Show version")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", envvar="DATAING_API_KEY", help="API key"),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--url", envvar="DATAING_BASE_URL", help="Backend URL"),
    ] = None,
) -> None:
    """Dataing CLI - Autonomous Data Quality Investigation."""
    if version:
        from dataing_cli import __version__

        console.print(f"dataing-cli {__version__}")
        raise typer.Exit()

    # Set up shared state
    state = State()
    state.verbose = verbose
    state.json_output = json_output
    state.api_key = api_key
    state.base_url = base_url
    ctx.obj = state

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


# Register subcommand groups
app.add_typer(run.app, name="run", help="Manage investigation runs")
app.add_typer(ds.app, name="ds", help="Manage datasources")


if __name__ == "__main__":
    app()
