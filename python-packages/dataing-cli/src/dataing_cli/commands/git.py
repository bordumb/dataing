"""Git repository connection management commands."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from dataing_cli.config import get_client
from dataing_cli.errors import cli_error_handler

app = typer.Typer()
console = Console()


def _git_request(
    client: Any,
    method: str,
    path: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Make a git API request using the client's internal request method."""
    response = client._request(method, path, **kwargs)
    result: dict[str, Any] = response.json()
    return result


@app.command("connect")
@cli_error_handler
def connect_repo(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Display name for the repository")],
    url: Annotated[str, typer.Argument(help="Repository URL (e.g., https://github.com/org/repo)")],
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="Git provider (github, gitlab, bitbucket)"),
    ] = "github",
    token: Annotated[
        str | None,
        typer.Option("--token", "-t", help="Access token for private repos"),
    ] = None,
    branch: Annotated[
        str,
        typer.Option("--branch", "-b", help="Default branch to track"),
    ] = "main",
    paths: Annotated[
        list[str] | None,
        typer.Option("--path", help="Paths to track (can be specified multiple times)"),
    ] = None,
) -> None:
    """Connect a git repository for pipeline change tracking."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    if provider not in ("github", "gitlab", "bitbucket"):
        console.print(
            f"[red]Error:[/red] Invalid provider '{provider}'. "
            "Must be github, gitlab, or bitbucket."
        )
        raise typer.Exit(1)

    payload: dict[str, Any] = {
        "name": name,
        "url": url,
        "provider": provider,
        "default_branch": branch,
    }
    if token:
        payload["access_token"] = token
    if paths:
        payload["tracked_paths"] = paths

    with console.status("Connecting repository..."):
        result = _git_request(client, "POST", "/api/v1/git/repos", json=payload)

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"[green]+[/green] Connected [cyan]{name}[/cyan] ({url})")
    console.print(f"  ID: {result['id']}")
    console.print(f"  Provider: {provider}")
    console.print(f"  Branch: {branch}")


@app.command("list")
@cli_error_handler
def list_repos(
    ctx: typer.Context,
    provider: Annotated[
        str | None,
        typer.Option("--provider", "-p", help="Filter by provider"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of results"),
    ] = 50,
) -> None:
    """List connected git repositories."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    params: dict[str, Any] = {"limit": limit}
    if provider:
        params["provider"] = provider

    result = _git_request(client, "GET", "/api/v1/git/repos", params=params)

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    items = result.get("items", [])
    if not items:
        console.print("[dim]No git repositories connected.[/dim]")
        return

    table = Table(title="Connected Git Repositories")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Provider")
    table.add_column("Branch")
    table.add_column("Status")
    table.add_column("Last Sync")

    for repo in items:
        status_style = {
            "synced": "green",
            "syncing": "yellow",
            "pending": "dim",
            "failed": "red",
        }.get(repo.get("sync_status", "pending"), "dim")

        last_sync = repo.get("last_sync_at")
        if last_sync:
            # Format datetime string for display
            last_sync = last_sync[:19].replace("T", " ")  # Simple truncation
        else:
            last_sync = "-"

        table.add_row(
            repo["id"][:8] + "...",
            repo["name"],
            repo["provider"],
            repo.get("default_branch", "main"),
            f"[{status_style}]{repo.get('sync_status', 'pending')}[/{status_style}]",
            last_sync,
        )

    console.print(table)


@app.command("sync")
@cli_error_handler
def sync_repo(
    ctx: typer.Context,
    repo_id: Annotated[str, typer.Argument(help="Repository ID to sync")],
) -> None:
    """Trigger a sync for a git repository."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    with console.status("Triggering sync..."):
        result = _git_request(client, "POST", f"/api/v1/git/repos/{repo_id}/sync")

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"[green]+[/green] {result.get('message', 'Sync triggered')}")
    console.print(f"  Status: {result.get('sync_status', 'syncing')}")


@app.command("changes")
@cli_error_handler
def list_changes(
    ctx: typer.Context,
    repo_id: Annotated[
        str | None,
        typer.Option("--repo", "-r", help="Repository ID to list changes for"),
    ] = None,
    asset: Annotated[
        str | None,
        typer.Option("--asset", "-a", help="Asset name to find related changes"),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Filter changes since date (YYYY-MM-DD)"),
    ] = None,
    until: Annotated[
        str | None,
        typer.Option("--until", help="Filter changes until date (YYYY-MM-DD)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of results"),
    ] = 50,
) -> None:
    """List code changes from connected repositories.

    Either --repo or --asset is required.
    """
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    if not repo_id and not asset:
        console.print("[red]Error:[/red] Either --repo or --asset is required.")
        raise typer.Exit(1)

    params: dict[str, Any] = {"limit": limit}
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    if asset:
        # Search by asset name across all repos
        params["asset_name"] = asset
        result = _git_request(client, "GET", "/api/v1/git/changes/by-asset", params=params)
    else:
        # List changes for a specific repo
        result = _git_request(client, "GET", f"/api/v1/git/repos/{repo_id}/changes", params=params)

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    items = result.get("items", [])
    if not items:
        console.print("[dim]No code changes found.[/dim]")
        return

    table = Table(title="Code Changes")
    table.add_column("Commit", style="dim")
    table.add_column("Author")
    table.add_column("Message")
    table.add_column("Date")
    table.add_column("Assets")

    for change in items:
        commit_hash = change.get("commit_hash", "")[:8]
        author = change.get("author_name") or change.get("author_email") or "-"
        message = change.get("message", "")
        if len(message) > 50:
            message = message[:47] + "..."

        committed_at = change.get("committed_at")
        if committed_at:
            committed_at = committed_at[:10]  # Just date
        else:
            committed_at = "-"

        affected = change.get("affected_assets", [])
        if affected:
            asset_names = [a.get("name", "") for a in affected[:3]]
            asset_str = ", ".join(asset_names)
            if len(affected) > 3:
                asset_str += f" (+{len(affected) - 3})"
        else:
            asset_str = "-"

        table.add_row(commit_hash, author, message, committed_at, asset_str)

    console.print(table)


@app.command("show")
@cli_error_handler
def show_repo(
    ctx: typer.Context,
    repo_id: Annotated[str, typer.Argument(help="Repository ID to show")],
) -> None:
    """Show details of a connected git repository."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    result = _git_request(client, "GET", f"/api/v1/git/repos/{repo_id}")

    if state and state.json_output:
        console.print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"[bold]{result['name']}[/bold]")
    console.print(f"  ID: {result['id']}")
    console.print(f"  URL: {result['url']}")
    console.print(f"  Provider: {result['provider']}")
    console.print(f"  Branch: {result.get('default_branch', 'main')}")

    status = result.get("sync_status", "pending")
    status_style = {
        "synced": "green",
        "syncing": "yellow",
        "pending": "dim",
        "failed": "red",
    }.get(status, "dim")
    console.print(f"  Status: [{status_style}]{status}[/{status_style}]")

    if result.get("sync_error"):
        console.print(f"  [red]Error: {result['sync_error']}[/red]")

    last_sync = result.get("last_sync_at")
    if last_sync:
        console.print(f"  Last Sync: {last_sync[:19].replace('T', ' ')}")

    tracked = result.get("tracked_paths")
    if tracked:
        console.print(f"  Tracked Paths: {', '.join(tracked)}")


@app.command("delete")
@cli_error_handler
def delete_repo(
    ctx: typer.Context,
    repo_id: Annotated[str, typer.Argument(help="Repository ID to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Disconnect and delete a git repository."""
    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    # Get repo details first
    repo = _git_request(client, "GET", f"/api/v1/git/repos/{repo_id}")

    if not force:
        confirm = typer.confirm(f"Delete repository '{repo['name']}' and all its code changes?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    _git_request(client, "DELETE", f"/api/v1/git/repos/{repo_id}")

    if state and state.json_output:
        console.print(json.dumps({"deleted": True}))
        return

    console.print(f"[green]+[/green] Deleted repository '{repo['name']}'")
