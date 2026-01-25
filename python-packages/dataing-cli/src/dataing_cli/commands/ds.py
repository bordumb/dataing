"""Datasource management commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from dataing_cli.config import get_client, load_config, save_config
from dataing_cli.errors import cli_error_handler

app = typer.Typer()
console = Console()


@app.command("list")
@cli_error_handler
def list_datasources(ctx: typer.Context) -> None:
    """List available datasources."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )
    datasources = client.list_datasources()

    if state and state.json_output:
        console.print(json.dumps([ds.model_dump() for ds in datasources], indent=2))
        return

    if not datasources:
        console.print("[dim]No datasources configured.[/dim]")
        return

    table = Table(title="Datasources")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Status")

    for ds in datasources:
        status = "[green]*[/green]" if ds.status == "connected" else "[red]*[/red]"
        id_display = f"{ds.id[:12]}..." if len(ds.id) > 12 else ds.id
        table.add_row(id_display, ds.name, ds.source_type, status)

    console.print(table)


@app.command("test")
@cli_error_handler
def test_datasource(
    ctx: typer.Context,
    datasource_id: Annotated[str, typer.Argument(help="Datasource ID to test")],
) -> None:
    """Test datasource connection."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    with console.status(f"Testing connection to {datasource_id}..."):
        result = client.test_datasource(datasource_id)

    if state and state.json_output:
        console.print(json.dumps(result.model_dump(), indent=2))
        return

    if result.success:
        msg = "[green]+[/green] Connection successful"
        if result.latency_ms:
            msg += f" ({result.latency_ms}ms)"
        console.print(msg)
    else:
        console.print(f"[red]-[/red] Connection failed: {result.message}")
        raise typer.Exit(1)


@app.command("attach")
@cli_error_handler
def attach_datasource(
    ctx: typer.Context,
    datasource_id: Annotated[str, typer.Argument(help="Datasource ID to set as default")],
) -> None:
    """Set default datasource for future commands."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    # Verify datasource exists
    datasources = client.list_datasources()
    ds = next((d for d in datasources if d.id == datasource_id), None)

    if not ds:
        console.print(f"[red]Error:[/red] Datasource {datasource_id} not found")
        raise typer.Exit(1)

    config = load_config()
    config["default_datasource_id"] = datasource_id
    config["default_datasource_name"] = ds.name
    save_config(config)

    console.print(f"[green]+[/green] Default datasource set to [cyan]{ds.name}[/cyan]")


@app.command("schema")
@cli_error_handler
def show_schema(
    ctx: typer.Context,
    datasource_id: Annotated[
        str | None,
        typer.Argument(help="Datasource ID (uses default if not specified)"),
    ] = None,
    table_filter: Annotated[
        str | None,
        typer.Option("--table", "-t", help="Filter to specific table"),
    ] = None,
) -> None:
    """Show datasource schema."""
    state = ctx.obj
    config = load_config()

    ds_id = datasource_id or config.get("default_datasource_id")
    if not ds_id:
        console.print(
            "[red]Error:[/red] No datasource specified. "
            "Use datasource_id argument or run 'dataing ds attach'"
        )
        raise typer.Exit(1)

    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )
    schema = client.get_schema(ds_id)

    if state and state.json_output:
        console.print(json.dumps(schema.model_dump(), indent=2))
        return

    if not schema.tables:
        console.print("[dim]No tables found.[/dim]")
        return

    for tbl in schema.tables:
        if table_filter and table_filter.lower() not in tbl.name.lower():
            continue

        console.print(f"\n[bold cyan]{tbl.name}[/bold cyan]")

        col_table = Table(show_header=True, box=None)
        col_table.add_column("Column")
        col_table.add_column("Type", style="dim")
        col_table.add_column("Nullable", style="dim")

        for col in tbl.columns:
            nullable = "+" if col.nullable else ""
            col_table.add_row(col.name, col.data_type, nullable)

        console.print(col_table)
