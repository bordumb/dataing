"""IPython magic commands for Dataing.

This module implements the %dataing magic command with subcommands:
- attach: Attach context from URN or SQL
- lineage: Display lineage graph
- ask: Start an investigation with streaming
- status: Show current context status
- clear: Clear current context
"""

from __future__ import annotations

import argparse
import shlex
import sys
from typing import TYPE_CHECKING, Any

from IPython.core.magic import Magics, line_magic, magics_class
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring

from .state import get_state, reset_state

if TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell


@magics_class
class DataingMagics(Magics):
    """IPython magic commands for Dataing data quality investigation.

    Usage:
        %load_ext dataing_notebook

        # Connect to API
        %dataing connect --api-key sk-xxx --base-url https://api.dataing.io

        # Attach context by URN
        %dataing attach postgres://db.schema.orders

        # Attach context from SQL
        %dataing attach "SELECT * FROM orders" --datasource ds-123

        # Display lineage
        %dataing lineage

        # Start an investigation
        %dataing ask "Why are there null values?"

        # Show current status
        %dataing status

        # Clear context
        %dataing clear
    """

    def __init__(self, shell: InteractiveShell) -> None:
        """Initialize the magic extension.

        Args:
            shell: IPython interactive shell instance.
        """
        super().__init__(shell)
        self._state = get_state()

    @line_magic
    def dataing(self, line: str) -> Any:
        """Main dataing magic command.

        Args:
            line: Command line arguments.

        Returns:
            Command result or None.
        """
        if not line.strip():
            return self._show_help()

        # Parse the subcommand
        parts = shlex.split(line)
        subcommand = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Dispatch to subcommand
        handlers = {
            "connect": self._handle_connect,
            "attach": self._handle_attach,
            "lineage": self._handle_lineage,
            "ask": self._handle_ask,
            "status": self._handle_status,
            "clear": self._handle_clear,
            "help": self._show_help,
        }

        handler = handlers.get(subcommand)
        if handler is None:
            print(f"Unknown subcommand: {subcommand}", file=sys.stderr)
            return self._show_help()

        return handler(args)

    def _show_help(self, args: list[str] | None = None) -> None:
        """Show help message."""
        help_text = """
Dataing Magic Commands
======================

%dataing connect [--api-key KEY] [--base-url URL]
    Connect to the Dataing API.

%dataing attach <URN|SQL> [--datasource ID] [--platform PLATFORM]
    Attach context from a URN or SQL query.
    Examples:
        %dataing attach postgres://db.schema.orders
        %dataing attach "SELECT * FROM orders" --datasource ds-123
        %dataing attach "SELECT * FROM orders" --platform postgres

%dataing lineage
    Display the lineage graph for the attached context.

%dataing ask "<question>"
    Start an investigation with the given question.
    Uses streaming to display progress.

%dataing status
    Show the current context status.

%dataing clear
    Clear the current context.

%dataing help
    Show this help message.
"""
        print(help_text)

    def _handle_connect(self, args: list[str]) -> None:
        """Handle connect subcommand.

        Args:
            args: Command arguments.
        """
        from dataing_sdk import DataingClient

        parser = argparse.ArgumentParser(prog="%dataing connect")
        parser.add_argument("--api-key", "-k", help="API key")
        parser.add_argument("--base-url", "-u", help="API base URL")
        parser.add_argument("--timeout", "-t", type=float, default=30.0, help="Timeout")

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        # Create client
        client = DataingClient(
            base_url=parsed.base_url,
            api_key=parsed.api_key,
            timeout=parsed.timeout,
        )

        self._state.client = client
        print(f"Connected to {client.base_url}")

    def _handle_attach(self, args: list[str]) -> None:
        """Handle attach subcommand.

        Args:
            args: Command arguments.
        """
        from dataing_sdk import DataingClient, ValidationError, from_sql

        if not args:
            print("Error: attach requires a URN or SQL query", file=sys.stderr)
            return

        parser = argparse.ArgumentParser(prog="%dataing attach")
        parser.add_argument("target", help="URN or SQL query")
        parser.add_argument("--datasource", "-d", help="Datasource ID")
        parser.add_argument("--platform", "-p", help="Default platform for SQL")

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        # Ensure client exists
        if self._state.client is None:
            self._state.client = DataingClient()
            print(f"Auto-connected to {self._state.client.base_url}")

        target = parsed.target
        datasource_id = parsed.datasource or self._state.default_datasource_id
        platform = parsed.platform or self._state.default_platform

        # Determine if target is URN or SQL
        is_sql = (
            target.upper().startswith("SELECT")
            or target.upper().startswith("WITH")
            or " FROM " in target.upper()
        )

        try:
            if is_sql:
                # Parse SQL to extract assets
                if not datasource_id and not platform:
                    print(
                        "Error: SQL query requires --datasource or --platform",
                        file=sys.stderr,
                    )
                    return

                assets = from_sql(
                    target,
                    datasource_id=datasource_id,
                    default_platform=platform,
                )

                if not assets:
                    print("Warning: No tables found in SQL query", file=sys.stderr)
                    return

                # Create context from assets
                ctx = self._state.client.context(
                    assets=assets,
                )
            else:
                # Treat as URN
                ctx = self._state.client.context(target)

            # Attach context
            self._state.attach_context(ctx)
            print(f"Attached context: {len(ctx.resolved_assets)} asset(s)")
            print(f"Bundle hash: {ctx.bundle_hash}")

        except ValidationError as e:
            print(f"Validation error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error attaching context: {e}", file=sys.stderr)

    def _handle_lineage(self, args: list[str]) -> None:
        """Handle lineage subcommand.

        Args:
            args: Command arguments.
        """
        if not self._state.is_attached:
            print("Error: No context attached. Use '%dataing attach' first.", file=sys.stderr)
            return

        ctx = self._state.context
        if ctx is None:
            return

        lineage = ctx.lineage
        if lineage is None:
            print("No lineage information available")
            return

        # Try to use rich for nice output
        try:
            from rich.console import Console
            from rich.tree import Tree

            console = Console()
            root_name = lineage.get("root", "Unknown")
            tree = Tree(f"[bold blue]{root_name}[/bold blue]")

            datasets = lineage.get("datasets", {})
            edges = lineage.get("edges", [])

            # Build tree from edges
            for edge in edges:
                source = edge.get("source", "?")
                target = edge.get("target", "?")
                edge_type = edge.get("edge_type", "transforms")
                tree.add(f"[green]{source}[/green] --[{edge_type}]--> [yellow]{target}[/yellow]")

            console.print(tree)

        except ImportError:
            # Fallback to plain text
            print("Lineage Graph:")
            print(f"  Root: {lineage.get('root', 'Unknown')}")
            datasets = lineage.get("datasets", {})
            if datasets:
                print(f"  Datasets: {len(datasets)}")
            edges = lineage.get("edges", [])
            for edge in edges:
                source = edge.get("source", "?")
                target = edge.get("target", "?")
                print(f"    {source} -> {target}")

    def _handle_ask(self, args: list[str]) -> None:
        """Handle ask subcommand.

        Args:
            args: Command arguments.
        """
        if not args:
            print("Error: ask requires a question", file=sys.stderr)
            return

        if not self._state.is_attached:
            print("Error: No context attached. Use '%dataing attach' first.", file=sys.stderr)
            return

        ctx = self._state.context
        if ctx is None or self._state.client is None:
            return

        # Join args as the question
        question = " ".join(args).strip('"\'')

        print(f"Starting investigation: {question}")
        print("---")

        try:
            # Start a run
            run = self._state.client.run(
                assets=ctx.assets,
                goal=question,
                bundle_id=ctx.bundle_id,
            )

            print(f"Run ID: {run.run_id}")
            print(f"Status: {run.status}")
            print(f"Events URL: {self._state.client.base_url}/api/v1/runs/{run.run_id}/events")

            # TODO: Implement SSE streaming when httpx-sse is available
            # For now, just show the run info

        except Exception as e:
            print(f"Error starting investigation: {e}", file=sys.stderr)

    def _handle_status(self, args: list[str]) -> None:
        """Handle status subcommand.

        Args:
            args: Command arguments.
        """
        print("Dataing Notebook Status")
        print("=======================")

        # Client status
        if self._state.client:
            print(f"API: {self._state.client.base_url}")
            print(f"API Key: {'***' if self._state.client.api_key else 'Not set'}")
        else:
            print("API: Not connected")

        # Context status
        if self._state.is_attached and self._state.context:
            ctx = self._state.context
            print(f"Context: Attached")
            print(f"  Bundle ID: {ctx.bundle_id[:16]}...")
            print(f"  Bundle Hash: {ctx.bundle_hash}")
            print(f"  Assets: {len(ctx.resolved_assets)}")
            for asset in ctx.resolved_assets:
                print(f"    - {asset.dataset_id}")
        else:
            print("Context: Not attached")

        # Cache status
        cache_count = len(self._state.bundle_cache)
        print(f"Cached bundles: {cache_count}")

    def _handle_clear(self, args: list[str]) -> None:
        """Handle clear subcommand.

        Args:
            args: Command arguments.
        """
        parser = argparse.ArgumentParser(prog="%dataing clear")
        parser.add_argument("--cache", "-c", action="store_true", help="Also clear cache")
        parser.add_argument("--all", "-a", action="store_true", help="Clear everything")

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        if parsed.all:
            reset_state()
            self._state = get_state()
            print("Cleared all state")
        else:
            self._state.clear_context()
            print("Cleared context")
            if parsed.cache:
                self._state.clear_cache()
                print("Cleared cache")


def load_ipython_extension(ipython: InteractiveShell) -> None:
    """Load the Dataing magic extension.

    Args:
        ipython: IPython interactive shell instance.
    """
    ipython.register_magics(DataingMagics)


def unload_ipython_extension(ipython: InteractiveShell) -> None:
    """Unload the Dataing magic extension.

    Args:
        ipython: IPython interactive shell instance.
    """
    # Reset state when unloading
    reset_state()
