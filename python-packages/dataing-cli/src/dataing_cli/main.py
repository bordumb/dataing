"""Dataing CLI - Autonomous Data Quality Investigation."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="dataing",
    help="Autonomous Data Quality Investigation CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
) -> None:
    """Dataing CLI - Autonomous Data Quality Investigation."""
    if version:
        from dataing_cli import __version__

        console.print(f"dataing-cli {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
