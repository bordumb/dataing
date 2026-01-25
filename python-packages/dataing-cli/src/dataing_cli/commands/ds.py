"""Datasource management commands."""

from __future__ import annotations

import typer

app = typer.Typer()


@app.command("list")
def list_datasources() -> None:
    """List available datasources."""
    typer.echo("DS list command (not yet implemented)")


@app.command("test")
def test_datasource() -> None:
    """Test datasource connection."""
    typer.echo("DS test command (not yet implemented)")


@app.command("attach")
def attach_datasource() -> None:
    """Set default datasource for future commands."""
    typer.echo("DS attach command (not yet implemented)")


@app.command("schema")
def show_schema() -> None:
    """Show datasource schema."""
    typer.echo("DS schema command (not yet implemented)")
