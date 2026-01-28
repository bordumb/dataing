"""Dataing CLI - Autonomous Data Quality Investigation."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from dataing_cli.commands import ask, ds, git, repo, run

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


@app.command()
def init(
    ctx: typer.Context,
    url: Annotated[
        str,
        typer.Option(
            "--url",
            "-u",
            prompt="Backend URL",
            help="Dataing backend URL",
        ),
    ] = "http://localhost:8000",
    api_key: Annotated[
        str,
        typer.Option(
            "--api-key",
            "-k",
            prompt=True,
            hide_input=True,
            help="API key for authentication",
        ),
    ] = ...,
    no_keyring: Annotated[
        bool,
        typer.Option(
            "--no-keyring",
            help="Store API key in config file instead of OS keychain",
        ),
    ] = False,
) -> None:
    """Initialize CLI configuration."""
    from dataing_sdk import DataingClient

    from dataing_cli.config import get_config_path, save_api_key, save_config

    # Test connection first
    with console.status("[bold blue]Testing connection..."):
        try:
            client = DataingClient(base_url=url, api_key=api_key)
            client.health()
        except Exception as e:
            console.print(f"[red]Connection failed:[/red] {e}")
            raise typer.Exit(1) from None

    # Save config
    save_config({"api_url": url})
    success, message = save_api_key(api_key, use_keyring=not no_keyring)

    if "less secure" in message.lower() or "warning" in message.lower():
        console.print(f"[yellow]Warning:[/yellow] {message}")

    console.print(f"[green]+[/green] Configuration saved to {get_config_path()}")


@app.command()
def status(ctx: typer.Context) -> None:
    """Check connection and show current configuration."""
    import json

    from dataing_cli.config import ConfigError, get_api_key, get_client, load_config
    from dataing_cli.display import print_status

    state = ctx.obj
    config = load_config()
    api_key = get_api_key(state.api_key if state else None)

    connected = False
    error = None

    try:
        client = get_client(
            api_key=state.api_key if state else None,
            base_url=state.base_url if state else None,
        )
        client.health()
        connected = True
    except ConfigError as e:
        error = str(e)
    except Exception as e:
        error = str(e)

    if state and state.json_output:
        result = {
            "connected": connected,
            "url": config.get("api_url"),
            "api_key_configured": bool(api_key),
            "default_datasource": config.get("default_datasource_name"),
        }
        if error:
            result["error"] = error
        console.print(json.dumps(result, indent=2))
    else:
        print_status(config, api_key, connected, error)

    if not connected:
        raise typer.Exit(1)


# Register subcommand groups
app.add_typer(run.app, name="run", help="Manage investigation runs")
app.add_typer(ds.app, name="ds", help="Manage datasources")
app.add_typer(ask.app, name="ask", help="Interactive investigation mode")
app.add_typer(repo.app, name="repo", help="Manage dataset-to-repository mappings")
app.add_typer(git.app, name="git", help="Manage git repository connections")


if __name__ == "__main__":
    app()
