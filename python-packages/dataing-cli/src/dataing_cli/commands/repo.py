"""Repository mapping management commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from dataing_cli.config import get_client
from dataing_cli.errors import cli_error_handler

app = typer.Typer()
console = Console()


@app.command("map")
@cli_error_handler
def map_repo(
    ctx: typer.Context,
    dataset: Annotated[str, typer.Argument(help="Dataset identifier (e.g., analytics.orders)")],
    repo: Annotated[str, typer.Argument(help="Repository as owner/repo (e.g., acme/etl)")],
    file_path: Annotated[
        str | None, typer.Option("--file-path", "-f", help="File path in repo")
    ] = None,
    branch: Annotated[str | None, typer.Option("--branch", "-b", help="Branch name")] = None,
    pattern_type: Annotated[str, typer.Option("--type", "-t", help="Pattern type")] = "exact",
) -> None:
    """Create an explicit dataset-to-repository mapping."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    parts = repo.split("/", 1)
    if len(parts) != 2:
        console.print("[red]Error:[/red] repo must be in owner/repo format")
        raise typer.Exit(1)

    repo_owner, repo_name = parts

    kwargs: dict[str, str] = {"pattern_type": pattern_type}
    if file_path:
        kwargs["file_path"] = file_path
    if branch:
        kwargs["branch"] = branch

    result = client.create_repo_mapping(
        dataset_pattern=dataset,
        repo_owner=repo_owner,
        repo_name=repo_name,
        **kwargs,
    )

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"[green]+[/green] Mapped [cyan]{dataset}[/cyan] -> {repo}")
    if file_path:
        console.print(f"  File: {file_path}")


@app.command("show")
@cli_error_handler
def show_repo(
    ctx: typer.Context,
    dataset: Annotated[str, typer.Argument(help="Dataset identifier to resolve")],
) -> None:
    """Resolve and display the repository mapping for a dataset."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    result = client.resolve_repo(dataset, include_all=True)

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    primary = result.get("primary")
    if not primary:
        console.print(f"[dim]No repo mapping found for {dataset}[/dim]")
        return

    console.print(f"[bold]{dataset}[/bold]")
    console.print(
        f"  [green]*[/green] {primary['repo_owner']}/{primary['repo_name']}"
        f" (confidence: {primary['confidence']:.0%}, source: {primary['source']})"
    )
    if primary.get("file_path"):
        console.print(f"  File: {primary['file_path']}")
    if primary.get("branch"):
        console.print(f"  Branch: {primary['branch']}")

    all_matches = result.get("all_matches") or []
    if len(all_matches) > 1:
        console.print(f"\n[dim]{len(all_matches) - 1} additional match(es):[/dim]")
        for m in all_matches[1:]:
            console.print(
                f"  - {m['repo_owner']}/{m['repo_name']}"
                f" (confidence: {m['confidence']:.0%}, source: {m['source']})"
            )


@app.command("list")
@cli_error_handler
def list_mappings(
    ctx: typer.Context,
    source: Annotated[str | None, typer.Option("--source", "-s", help="Filter by source")] = None,
    suggestions: Annotated[
        bool, typer.Option("--suggestions", help="Show only suggestions")
    ] = False,
) -> None:
    """List all dataset-to-repository mappings."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    mappings = client.list_repo_mappings(source=source, suggestions_only=suggestions)

    if state and state.json_output:
        console.print(json.dumps(mappings, indent=2, default=str))
        return

    if not mappings:
        label = "suggestions" if suggestions else "mappings"
        console.print(f"[dim]No {label} found.[/dim]")
        return

    table = Table(title="Suggestions" if suggestions else "Repository Mappings")
    table.add_column("Pattern", style="cyan")
    table.add_column("Type")
    table.add_column("Repository")
    table.add_column("File")
    table.add_column("Source")
    table.add_column("Confidence")
    if not suggestions:
        table.add_column("Confirmed")

    for m in mappings:
        row = [
            m["dataset_pattern"],
            m["pattern_type"],
            f"{m['repo_owner']}/{m['repo_name']}",
            m.get("file_path") or "",
            m["source"],
            f"{m['confidence']:.0%}",
        ]
        if not suggestions:
            confirmed = "[green]*[/green]" if m.get("confirmed") else "[yellow]?[/yellow]"
            row.append(confirmed)
        table.add_row(*row)

    console.print(table)


@app.command("confirm")
@cli_error_handler
def confirm_mapping(
    ctx: typer.Context,
    mapping_id: Annotated[str, typer.Argument(help="Mapping ID to confirm")],
) -> None:
    """Confirm a suggested repository mapping."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    result = client.confirm_repo_mapping(mapping_id)

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    console.print(
        f"[green]+[/green] Confirmed mapping: {result['dataset_pattern']}"
        f" -> {result['repo_owner']}/{result['repo_name']}"
    )


@app.command("dismiss")
@cli_error_handler
def dismiss_mapping(
    ctx: typer.Context,
    mapping_id: Annotated[str, typer.Argument(help="Mapping ID to dismiss")],
) -> None:
    """Dismiss a suggested repository mapping."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    client.dismiss_repo_mapping(mapping_id)

    if state and state.json_output:
        console.print(json.dumps({"dismissed": True}))
        return

    console.print(f"[green]+[/green] Dismissed mapping {mapping_id}")


@app.command("import-dbt")
@cli_error_handler
def import_dbt(
    ctx: typer.Context,
    manifest_path: Annotated[Path, typer.Argument(help="Path to dbt manifest.json")],
    repo: Annotated[str, typer.Option("--repo", "-r", help="Repository as owner/repo")] = ...,
    branch: Annotated[str | None, typer.Option("--branch", "-b", help="Branch name")] = None,
) -> None:
    """Import repository mappings from a dbt manifest.json."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    if not manifest_path.exists():
        console.print(f"[red]Error:[/red] File not found: {manifest_path}")
        raise typer.Exit(1)

    parts = repo.split("/", 1)
    if len(parts) != 2:
        console.print("[red]Error:[/red] --repo must be in owner/repo format")
        raise typer.Exit(1)

    repo_owner, repo_name = parts
    content = manifest_path.read_bytes()

    with console.status("Importing dbt manifest..."):
        result = client.import_dbt_manifest(
            manifest_content=content,
            repo_owner=repo_owner,
            repo_name=repo_name,
            branch=branch,
        )

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"[green]+[/green] Imported {result.get('imported', 0)} models from dbt manifest")
    if result.get("skipped", 0) > 0:
        console.print(f"[yellow]![/yellow] Skipped {result['skipped']} models")
