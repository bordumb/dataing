"""Error handling for CLI."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

import typer
from dataing_sdk.exceptions import (
    AmbiguousAssetError,
    AuthError,
    DataingError,
    NotFoundError,
    RateLimitError,
    ServerError,
    StreamError,
    ValidationError,
)
from dataing_sdk.exceptions import (
    TimeoutError as DataingTimeoutError,
)
from rich.console import Console

console = Console()

F = TypeVar("F", bound=Callable[..., Any])


class CLIError(Exception):
    """Base CLI error with exit code."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        """Initialize CLI error.

        Args:
            message: Error message to display.
            exit_code: Exit code to use (default 1).
        """
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


def handle_sdk_error(exc: DataingError) -> None:
    """Map SDK exceptions to CLI output and exit.

    Args:
        exc: The SDK exception to handle.

    Raises:
        typer.Exit: Always exits with appropriate exit code.
    """
    if isinstance(exc, AuthError):
        console.print("[red]Authentication failed.[/red] Check your API key.")
        console.print("[dim]Hint: Run 'dataing init' to configure credentials.[/dim]")
        raise typer.Exit(1)

    if isinstance(exc, NotFoundError):
        console.print(f"[red]Not found:[/red] {exc}")
        raise typer.Exit(1)

    if isinstance(exc, RateLimitError):
        retry_after = exc.retry_after or 60
        console.print(f"[yellow]Rate limited.[/yellow] Retry after {retry_after:.0f} seconds.")
        raise typer.Exit(1)

    if isinstance(exc, ValidationError):
        console.print(f"[red]Invalid input:[/red] {exc}")
        raise typer.Exit(2)

    if isinstance(exc, AmbiguousAssetError):
        console.print("[yellow]Ambiguous asset.[/yellow] Multiple matches found:")
        for candidate in exc.candidates:
            name = candidate.get("name", candidate.get("id", "unknown"))
            ds_id = candidate.get("id", "")
            console.print(f"  - {name} ({ds_id})")
        console.print("\n[dim]Hint: Specify the full asset name or datasource.[/dim]")
        raise typer.Exit(1)

    if isinstance(exc, ServerError):
        console.print(f"[red]Server error:[/red] {exc}")
        console.print("[dim]Hint: The service may be temporarily unavailable.[/dim]")
        raise typer.Exit(1)

    if isinstance(exc, DataingTimeoutError):
        console.print("[red]Request timed out.[/red]")
        console.print("[dim]Hint: Try again or check network connectivity.[/dim]")
        raise typer.Exit(1)

    if isinstance(exc, StreamError):
        console.print(f"[red]Streaming error:[/red] {exc}")
        console.print("[dim]Hint: The stream may have been interrupted.[/dim]")
        raise typer.Exit(1)

    # Generic DataingError
    console.print(f"[red]Error:[/red] {exc}")
    raise typer.Exit(1)


def handle_connection_error(exc: Exception) -> None:
    """Handle connection-related errors.

    Args:
        exc: The connection exception.

    Raises:
        typer.Exit: Exits with code 1.
    """
    console.print(f"[red]Connection failed:[/red] {exc}")
    console.print("[dim]Hint: Check network connectivity and backend URL.[/dim]")
    raise typer.Exit(1)


def cli_error_handler(func: F) -> F:
    """Decorator to wrap commands with error handling.

    This decorator catches SDK exceptions and connection errors,
    converting them to user-friendly CLI output before exiting.

    Args:
        func: The command function to wrap.

    Returns:
        Wrapped function with error handling.

    Example:
        ```python
        @app.command()
        @cli_error_handler
        def my_command():
            # SDK errors will be handled automatically
            client.list_datasources()
        ```
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except DataingError as e:
            handle_sdk_error(e)
        except CLIError as e:
            console.print(f"[red]Error:[/red] {e.message}")
            raise typer.Exit(e.exit_code) from None
        except (OSError, ConnectionError) as e:
            handle_connection_error(e)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
            raise typer.Exit(130) from None

    return wrapper  # type: ignore[return-value]
