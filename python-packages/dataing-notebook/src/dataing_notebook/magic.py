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

from .state import get_state, reset_state

if TYPE_CHECKING:
    from IPython.core.interactiveshell import InteractiveShell

# Server extension state endpoint for JupyterLab sync
STATE_ENDPOINT = "dataing/state"


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

    def _get_jupyter_server_url(self) -> str | None:
        """Get the Jupyter server URL from environment.

        Returns:
            Server URL or None if not in Jupyter environment.
        """
        import os

        # In JupyterLab, JUPYTER_SERVER_URL or notebook app URL
        # Try common environment variables
        for var in ["JUPYTER_SERVER_URL", "JPY_SESSION_NAME"]:
            if var in os.environ:
                # Construct from session name
                pass

        # Fallback: use localhost with default port
        # The server extension is at the same origin as the notebook
        return "http://localhost:8888"

    def _send_state_update(self) -> None:
        """Send current state to JupyterLab frontend via HTTP POST."""
        import json
        import urllib.error
        import urllib.request

        state_data = {
            "attached_datasource": None,
            "bundle_id": None,
            "bundle_hash": None,
            "current_run_id": None,
        }

        if self._state.is_attached and self._state.context:
            ctx = self._state.context
            # Get datasource name from first resolved asset
            if ctx.resolved_assets:
                first_asset = ctx.resolved_assets[0]
                state_data["attached_datasource"] = first_asset.dataset_id
            state_data["bundle_id"] = ctx.bundle_id
            state_data["bundle_hash"] = ctx.bundle_hash

        # Get current run if any
        for entry in reversed(self._state._history):
            if entry.get("action") == "ask":
                state_data["current_run_id"] = entry.get("run_id")
                break

        try:
            # Get Jupyter server URL
            server_url = self._get_jupyter_server_url()
            if not server_url:
                return

            # Build URL to state endpoint
            url = f"{server_url.rstrip('/')}/{STATE_ENDPOINT}"

            # POST state to server extension
            data = json.dumps(state_data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=5):
                # State update sent successfully
                pass

        except urllib.error.URLError:
            # Server extension not available - that's OK
            pass
        except Exception:
            # Any other error - silent fail
            pass

    @line_magic
    def dataing(self, line: str) -> None:
        """Main dataing magic command.

        Args:
            line: Command line arguments.
        """
        if not line.strip():
            self._show_help()
            return

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
            "export": self._handle_export,
            "status": self._handle_status,
            "clear": self._handle_clear,
            "history": self._handle_history,
            "replay": self._handle_replay,
            "compare": self._handle_compare,
            "help": self._show_help,
        }

        handler = handlers.get(subcommand)
        if handler is None:
            print(f"Unknown subcommand: {subcommand}", file=sys.stderr)
            self._show_help()
            return

        handler(args)

    def _show_help(self, args: list[str] | None = None) -> None:
        """Show help message."""
        help_text = """
Dataing Magic Commands
======================

%dataing connect [--api-key KEY] [--base-url URL]
    Connect to the Dataing API.
    Without arguments, uses saved GUI configuration if available.
    Prints reproducible snippet after connection.

%dataing attach <URN|SQL> [--datasource ID] [--platform PLATFORM]
    Attach context from a URN or SQL query.
    Examples:
        %dataing attach postgres://db.schema.orders
        %dataing attach "SELECT * FROM orders" --datasource ds-123
        %dataing attach "SELECT * FROM orders" --platform postgres

%dataing lineage [--depth N] [--direction upstream|downstream|both] [--export FILE]
    Display the lineage graph for the attached context.
    Options:
        --depth, -d N        Max traversal depth, 1-10 (default: 2)
        --direction DIR      upstream, downstream, or both (default: both)
        --export, -e FILE    Export graph to PNG or SVG file

%dataing ask "<question>"
    Start an investigation with the given question.
    Uses streaming to display progress.

%dataing export [--format FORMAT] [--output FILE]
    Export the last investigation as a markdown incident report.
    Formats: markdown (default), json

%dataing status
    Show the current context status (same info as sidebar).

%dataing clear
    Clear the current context.

%dataing history [--dataset ID] [--days N] [--limit N] [--offset N]
    List past investigations from the API.
    Options:
        --dataset, -d ID     Filter by dataset ID
        --days, -n N         Show investigations from last N days (default: 30)
        --limit, -l N        Max results to return (default: 20)
        --offset N           Pagination offset (default: 0)

%dataing replay <investigation_id> [--format rich|plain]
    Load and display a past investigation with all evidence.
    Options:
        --format, -f FORMAT  Output format: rich (default) or plain

%dataing compare <id1> <id2> [--format rich|plain]
    Compare two investigations side-by-side.
    Shows differences in synthesis, evidence, and hypotheses.
    Options:
        --format, -f FORMAT  Output format: rich (default) or plain

%dataing help
    Show this help message.
"""
        print(help_text)

    def _handle_history(self, args: list[str]) -> None:
        """Handle history subcommand -- list past investigations.

        Args:
            args: Command arguments.
        """
        from datetime import UTC, datetime, timedelta

        parser = argparse.ArgumentParser(prog="%dataing history")
        parser.add_argument("--dataset", "-d", help="Filter by dataset ID")
        parser.add_argument(
            "--days",
            "-n",
            type=int,
            default=30,
            help="Show investigations from last N days",
        )
        parser.add_argument(
            "--limit",
            "-l",
            type=int,
            default=20,
            help="Max results to return",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="Pagination offset",
        )

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        if self._state.client is None:
            print("Error: Not connected. Use '%dataing connect' first.", file=sys.stderr)
            return

        try:
            # Call the investigations list endpoint
            response = self._state.client._request("GET", "/api/v1/investigations")
            investigations = response.json()

            if not investigations:
                print("No investigations found.")
                return

            # Client-side filtering by date (days)
            cutoff_date = datetime.now(UTC) - timedelta(days=parsed.days)
            filtered = []
            for inv in investigations:
                created_str = inv.get("created_at", "")
                try:
                    # Parse ISO format date
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    if created >= cutoff_date:
                        filtered.append(inv)
                except (ValueError, TypeError):
                    # Include if we can't parse the date
                    filtered.append(inv)

            # Client-side filtering by dataset
            if parsed.dataset:
                filtered = [
                    inv
                    for inv in filtered
                    if parsed.dataset.lower() in inv.get("dataset_id", "").lower()
                ]

            # Apply pagination
            total = len(filtered)
            filtered = filtered[parsed.offset : parsed.offset + parsed.limit]

            if not filtered:
                print("No investigations match the filter criteria.")
                return

            # Render as plain text table
            self._render_history_table(filtered, total, parsed.offset, parsed.limit)

        except Exception as e:
            print(f"Error fetching investigations: {e}", file=sys.stderr)

    def _render_history_table(
        self,
        investigations: list[dict[str, Any]],
        total: int,
        offset: int,
        limit: int,
    ) -> None:
        """Render investigation history as a plain text table.

        Args:
            investigations: List of investigation dicts.
            total: Total count before pagination.
            offset: Current offset.
            limit: Page size.
        """
        # Column headers and widths
        headers = ["ID", "Dataset", "Status", "Created"]
        widths = [36, 30, 12, 20]

        # Print header
        header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
        print(header_line)
        print("-" * len(header_line))

        # Print rows
        for inv in investigations:
            inv_id = str(inv.get("investigation_id", ""))[:36]
            dataset = inv.get("dataset_id", "")[:30]
            status = inv.get("status", "unknown")[:12]
            created = inv.get("created_at", "")[:20]

            row = [
                inv_id.ljust(widths[0]),
                dataset.ljust(widths[1]),
                status.ljust(widths[2]),
                created.ljust(widths[3]),
            ]
            print("  ".join(row))

        # Print pagination info
        showing_end = min(offset + limit, total)
        print("")
        print(f"Showing {offset + 1}-{showing_end} of {total} investigations")
        if showing_end < total:
            print(f"Use --offset {showing_end} to see more")

    def _handle_replay(self, args: list[str]) -> None:
        """Handle replay subcommand -- load a past investigation.

        Args:
            args: Command arguments.
        """
        parser = argparse.ArgumentParser(prog="%dataing replay")
        parser.add_argument("investigation_id", help="Investigation UUID to replay")
        parser.add_argument(
            "--format",
            "-f",
            choices=["rich", "plain"],
            default="rich",
            help="Output format",
        )

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        if self._state.client is None:
            print("Error: Not connected. Use '%dataing connect' first.", file=sys.stderr)
            return

        try:
            # Fetch full investigation state from API
            investigation = self._state.client.get_investigation(parsed.investigation_id)

            # Store in session history for export
            self._state._history.append(
                {
                    "action": "replay",
                    "investigation_id": parsed.investigation_id,
                    "investigation": {
                        "investigation_id": investigation.investigation_id,
                        "status": investigation.status,
                        "main_branch": {
                            "branch_id": investigation.main_branch.branch_id,
                            "status": investigation.main_branch.status,
                            "current_step": investigation.main_branch.current_step,
                            "synthesis": investigation.main_branch.synthesis,
                            "evidence": investigation.main_branch.evidence,
                        },
                        "root_hash": investigation.root_hash,
                    },
                }
            )

            # Render investigation details
            self._render_replay(investigation, parsed.format)

        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                print(
                    f"Error: Investigation not found: {parsed.investigation_id}",
                    file=sys.stderr,
                )
            else:
                print(f"Error fetching investigation: {e}", file=sys.stderr)

    def _render_replay(self, investigation: Any, fmt: str) -> None:
        """Render a replayed investigation.

        Args:
            investigation: InvestigationState object from SDK.
            fmt: Output format ('rich' or 'plain').
        """
        print("=" * 60)
        print("INVESTIGATION REPLAY")
        print("=" * 60)
        print(f"ID:     {investigation.investigation_id}")
        print(f"Status: {investigation.status}")
        if investigation.root_hash:
            print(f"Hash:   {investigation.root_hash[:16]}...")
        print("")

        main_branch = investigation.main_branch

        # Show synthesis if available (completed investigations)
        if main_branch.synthesis:
            print("-" * 40)
            print("ROOT CAUSE ANALYSIS")
            print("-" * 40)
            synthesis = main_branch.synthesis
            if isinstance(synthesis, dict):
                if "root_cause" in synthesis:
                    print(f"\n{synthesis['root_cause']}")
                if "summary" in synthesis:
                    print(f"\nSummary: {synthesis['summary']}")
                if "recommendations" in synthesis:
                    print("\nRecommendations:")
                    recs = synthesis["recommendations"]
                    if isinstance(recs, list):
                        for rec in recs:
                            print(f"  • {rec}")
                    else:
                        print(f"  {recs}")
            else:
                print(str(synthesis))
            print("")

        # Show evidence
        evidence_list = main_branch.evidence
        if evidence_list:
            print("-" * 40)
            print(f"EVIDENCE ({len(evidence_list)} items)")
            print("-" * 40)

            for i, evidence in enumerate(evidence_list, 1):
                self._render_evidence_item(evidence, i, fmt)
        else:
            print("No evidence collected yet.")

        # Show current step for running investigations
        if investigation.status in ("running", "queued"):
            print("")
            print(f"Current Step: {main_branch.current_step}")

        print("")
        print("=" * 60)

    def _render_evidence_item(self, evidence: dict[str, Any], index: int, fmt: str) -> None:
        """Render a single evidence item.

        Args:
            evidence: Evidence dict from API.
            index: Evidence item number.
            fmt: Output format.
        """
        kind = evidence.get("kind", "unknown")
        print(f"\n[{index}] {kind.upper()}")

        if kind == "sql_result":
            # SQL evidence
            sql = evidence.get("sql", "")
            if sql:
                print(f"  SQL: {sql[:100]}{'...' if len(sql) > 100 else ''}")
            rows = evidence.get("row_count", evidence.get("rows", "?"))
            print(f"  Rows: {rows}")
            conclusion = evidence.get("conclusion", "")
            if conclusion:
                print(f"  Conclusion: {conclusion}")

        elif kind == "metric":
            # Metric evidence
            metric = evidence.get("metric", "")
            value = evidence.get("value", "")
            print(f"  Metric: {metric} = {value}")

        elif kind == "hypothesis":
            # Hypothesis
            hypothesis = evidence.get("hypothesis", evidence.get("text", ""))
            status = evidence.get("status", "")
            print(f"  Hypothesis: {hypothesis}")
            if status:
                print(f"  Status: {status}")

        else:
            # Generic evidence
            for key, value in evidence.items():
                if key not in ("kind", "seq", "prev_hash", "hash"):
                    val_str = str(value)
                    if len(val_str) > 100:
                        val_str = val_str[:100] + "..."
                    print(f"  {key}: {val_str}")

    def _handle_compare(self, args: list[str]) -> None:
        """Handle compare subcommand -- diff two investigations.

        Args:
            args: Command arguments.
        """
        parser = argparse.ArgumentParser(prog="%dataing compare")
        parser.add_argument("id1", help="First investigation UUID")
        parser.add_argument("id2", help="Second investigation UUID")
        parser.add_argument(
            "--format",
            "-f",
            choices=["rich", "plain"],
            default="rich",
            help="Output format",
        )

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        if self._state.client is None:
            print("Error: Not connected. Use '%dataing connect' first.", file=sys.stderr)
            return

        # Fetch both investigations
        try:
            inv1 = self._state.client.get_investigation(parsed.id1)
        except Exception as e:
            print(f"Error fetching investigation {parsed.id1}: {e}", file=sys.stderr)
            return

        try:
            inv2 = self._state.client.get_investigation(parsed.id2)
        except Exception as e:
            print(f"Error fetching investigation {parsed.id2}: {e}", file=sys.stderr)
            return

        self._render_comparison(inv1, inv2, parsed.format)

    def _render_comparison(self, inv1: Any, inv2: Any, fmt: str) -> None:
        """Render side-by-side comparison of two investigations.

        Args:
            inv1: First InvestigationState.
            inv2: Second InvestigationState.
            fmt: Output format ('rich' or 'plain').
        """
        # Column width for each side
        col_width = 40

        def truncate(s: str, width: int) -> str:
            return s[: width - 3] + "..." if len(s) > width else s.ljust(width)

        print("=" * (col_width * 2 + 5))
        print("INVESTIGATION COMPARISON")
        print("=" * (col_width * 2 + 5))
        print("")

        # Header comparison
        print(
            f"{'ID:':<8}{truncate(inv1.investigation_id, col_width)}  |  "
            f"{truncate(inv2.investigation_id, col_width)}"
        )
        print(
            f"{'Status:':<8}{truncate(inv1.status, col_width)}  |  "
            f"{truncate(inv2.status, col_width)}"
        )

        # Show status diff if different
        if inv1.status != inv2.status:
            print("         ^ STATUS DIFFERS ^")
        print("")

        # Synthesis comparison
        print("-" * (col_width * 2 + 5))
        print("SYNTHESIS / ROOT CAUSE")
        print("-" * (col_width * 2 + 5))

        synth1 = inv1.main_branch.synthesis
        synth2 = inv2.main_branch.synthesis

        root1 = self._extract_root_cause(synth1)
        root2 = self._extract_root_cause(synth2)

        if root1 or root2:
            print(f"Left:  {truncate(root1 or '(none)', col_width * 2)}")
            print(f"Right: {truncate(root2 or '(none)', col_width * 2)}")
            if root1 != root2:
                print("  ^ DIFFERS ^")
        else:
            print("(No synthesis available for either investigation)")
        print("")

        # Evidence comparison
        print("-" * (col_width * 2 + 5))
        print("EVIDENCE COMPARISON")
        print("-" * (col_width * 2 + 5))

        evidence1 = inv1.main_branch.evidence
        evidence2 = inv2.main_branch.evidence

        # Create evidence signatures for comparison
        sigs1 = {self._evidence_signature(e): e for e in evidence1}
        sigs2 = {self._evidence_signature(e): e for e in evidence2}

        shared = set(sigs1.keys()) & set(sigs2.keys())
        only_in_1 = set(sigs1.keys()) - set(sigs2.keys())
        only_in_2 = set(sigs2.keys()) - set(sigs1.keys())

        print(f"Shared evidence items: {len(shared)}")
        print(f"Only in left:  {len(only_in_1)}")
        print(f"Only in right: {len(only_in_2)}")
        print("")

        if only_in_1:
            print("Unique to LEFT:")
            for sig in list(only_in_1)[:5]:
                ev = sigs1[sig]
                kind = ev.get("kind", "unknown")
                print(f"  - [{kind}] {sig[:60]}")
            if len(only_in_1) > 5:
                print(f"  ... and {len(only_in_1) - 5} more")
            print("")

        if only_in_2:
            print("Unique to RIGHT:")
            for sig in list(only_in_2)[:5]:
                ev = sigs2[sig]
                kind = ev.get("kind", "unknown")
                print(f"  - [{kind}] {sig[:60]}")
            if len(only_in_2) > 5:
                print(f"  ... and {len(only_in_2) - 5} more")
            print("")

        print("=" * (col_width * 2 + 5))

    def _extract_root_cause(self, synthesis: dict[str, Any] | None) -> str:
        """Extract root cause string from synthesis dict.

        Args:
            synthesis: Synthesis dict or None.

        Returns:
            Root cause string or empty string.
        """
        if not synthesis:
            return ""
        if isinstance(synthesis, dict):
            return str(synthesis.get("root_cause", synthesis.get("summary", "")))
        return str(synthesis)

    def _evidence_signature(self, evidence: dict[str, Any]) -> str:
        """Create a signature for evidence comparison.

        Args:
            evidence: Evidence dict.

        Returns:
            Signature string for comparison.
        """
        kind = evidence.get("kind", "")
        if kind == "sql_result":
            sql = evidence.get("sql", "")
            return f"sql:{sql[:100]}"
        elif kind == "metric":
            metric = evidence.get("metric", "")
            return f"metric:{metric}"
        elif kind == "hypothesis":
            hyp = evidence.get("hypothesis", evidence.get("text", ""))
            return f"hypothesis:{hyp[:100]}"
        else:
            # Use first significant key-value
            for k, v in evidence.items():
                if k not in ("kind", "seq", "prev_hash", "hash"):
                    return f"{kind}:{k}:{str(v)[:50]}"
            return f"{kind}:unknown"

    def _handle_connect(self, args: list[str]) -> None:
        """Handle connect subcommand.

        If no args provided, tries to use saved GUI config from server extension.
        Prints reproducible snippet after successful connection.

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

        base_url = parsed.base_url
        api_key = parsed.api_key
        credential_mode = None

        # If no args provided, try to read from server extension
        if not base_url and not api_key:
            gui_config = self._get_gui_config()
            if gui_config:
                base_url = gui_config.get("base_url")
                api_key = gui_config.get("api_key")
                credential_mode = gui_config.get("mode")

                if base_url and api_key:
                    print("Using saved GUI configuration")

        # Create client
        client = DataingClient(
            base_url=base_url,
            api_key=api_key,
            timeout=parsed.timeout,
        )

        self._state.client = client
        self._state._credential_mode = credential_mode

        # Print connection info with reproducible snippet
        print(f"Connected to {client.base_url}")
        self._print_connect_snippet(client.base_url, credential_mode)

    def _get_gui_config(self) -> dict[str, Any] | None:
        """Get saved config from JupyterLab server extension.

        Returns:
            Dictionary with base_url, api_key, mode or None if not available.
        """
        import json
        import urllib.error
        import urllib.request

        try:
            server_url = self._get_jupyter_server_url()
            if not server_url:
                return None

            # Fetch credentials from server extension
            url = f"{server_url.rstrip('/')}/dataing/credentials"
            req = urllib.request.Request(url, method="GET")

            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("has_api_key"):
                    return {
                        "base_url": data.get("base_url"),
                        "api_key": data.get("api_key"),
                        "mode": data.get("mode"),
                    }
                return None

        except (urllib.error.URLError, json.JSONDecodeError):
            return None
        except Exception:
            return None

    def _print_connect_snippet(self, base_url: str, credential_mode: str | None) -> None:
        """Print reproducible snippet after connection.

        Args:
            base_url: The connected backend URL.
            credential_mode: The credential storage mode (keychain/env_var/session).
        """
        mode_descriptions = {
            "keychain": "OS Keychain",
            "env_var": "DATAING_API_KEY environment variable",
            "session": "session storage (not persisted)",
        }

        mode_desc = mode_descriptions.get(credential_mode or "", "unknown")

        print("")
        print("# Reproducible snippet:")
        print(f"#   %dataing connect --base-url {base_url}")
        print(f"# Auth: using {mode_desc}")
        if credential_mode == "env_var":
            print("# (API key loaded from DATAING_API_KEY)")
        elif credential_mode == "keychain":
            print("# (API key stored securely in OS keychain)")

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

            # Notify JupyterLab frontend
            self._send_state_update()

        except ValidationError as e:
            print(f"Validation error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error attaching context: {e}", file=sys.stderr)

    def _handle_lineage(self, args: list[str]) -> None:
        """Handle lineage subcommand with interactive graph visualization.

        Args:
            args: Command arguments.
        """
        parser = argparse.ArgumentParser(prog="%dataing lineage", add_help=False)
        parser.add_argument(
            "--depth",
            "-d",
            type=int,
            default=2,
            choices=range(1, 11),
            metavar="N",
            help="Max traversal depth from root, 1-10 (default: 2)",
        )
        parser.add_argument(
            "--direction",
            choices=["upstream", "downstream", "both"],
            default="both",
            help="Traversal direction (default: both)",
        )
        parser.add_argument(
            "--export",
            "-e",
            help="Export graph to file (e.g., lineage.png or lineage.svg)",
        )
        parser.add_argument("--help", "-h", action="store_true")

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        if parsed.help:
            parser.print_help()
            return

        if not self._state.is_attached:
            print(
                "Error: No context attached. Use '%dataing attach' first.",
                file=sys.stderr,
            )
            return

        ctx = self._state.context
        if ctx is None:
            return

        lineage = ctx.lineage
        if lineage is None or not lineage:
            print("No lineage information available for this context.")
            print("(Lineage requires a configured lineage provider like dbt or Airflow)")
            return

        if parsed.export:
            from .lineage_graph import export_lineage_graph

            export_path = parsed.export
            fmt = "svg" if export_path.endswith(".svg") else "png"
            try:
                result_path = export_lineage_graph(
                    lineage,
                    export_path,
                    fmt=fmt,
                    depth=parsed.depth,
                    direction=parsed.direction,
                )
                print(f"Graph exported to: {result_path}")
            except (ImportError, ValueError) as e:
                print(f"Export error: {e}", file=sys.stderr)
            return

        from .lineage_graph import render_lineage_graph

        widget = render_lineage_graph(
            lineage,
            depth=parsed.depth,
            direction=parsed.direction,
        )

        if widget is not None:
            from IPython.display import display  # type: ignore[import-untyped]

            display(widget)

    def _handle_ask(self, args: list[str]) -> None:
        """Handle ask subcommand with streaming timeline.

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

        # Parse arguments
        parser = argparse.ArgumentParser(prog="%dataing ask")
        parser.add_argument("question", nargs="*", help="Investigation question")
        parser.add_argument("--no-stream", action="store_true", help="Use polling instead")

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        question = " ".join(parsed.question).strip("\"'")
        if not question:
            print("Error: ask requires a question", file=sys.stderr)
            return

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
            print(f"Status: {run.status.value}")
            print("")

            # Store run for later reference
            self._state._history.append(
                {
                    "action": "ask",
                    "run_id": run.run_id,
                    "question": question,
                }
            )

            # Notify JupyterLab frontend about new run
            self._send_state_update()

            if parsed.no_stream:
                # Fallback to polling
                self._poll_for_completion(run)
            else:
                # Use streaming
                self._stream_events(run)

        except Exception as e:
            print(f"Error starting investigation: {e}", file=sys.stderr)

    def _stream_events(self, run: Any) -> None:
        """Stream SSE events for a run with timeline display.

        Args:
            run: The Run object to stream events from.
        """
        from .rendering import render_timeline_event

        print("Streaming events...")
        print("")

        events: list[dict[str, Any]] = []
        final_status = "running"

        try:
            for event in self._state.client.stream_run(run.run_id):
                events.append(
                    {
                        "seq": event.seq,
                        "event": event.event,
                        "data": event.data,
                        "timestamp": event.timestamp,
                    }
                )

                # Render the event
                render_timeline_event(event)

                if event.is_terminal:
                    final_status = "completed" if event.event == "run_completed" else "failed"
                    break

        except Exception as e:
            print(f"Stream error: {e}", file=sys.stderr)
            final_status = "error"

        print("")
        print("---")
        print(f"Investigation {final_status}")

        # Show clickable link
        self._show_ui_link(run.run_id)

        # Store events for export
        self._state._history.append(
            {
                "action": "stream_complete",
                "run_id": run.run_id,
                "events": events,
                "status": final_status,
            }
        )

    def _poll_for_completion(self, run: Any) -> None:
        """Poll for run completion (fallback method).

        Args:
            run: The Run object to poll.
        """
        print("Waiting for results (polling every 2s)...")

        def on_progress(r: Any) -> None:
            print(f"  Status: {r.status.value}", end="\r")

        try:
            final_run = self._state.client.wait_for_run(
                run.run_id,
                poll_interval=2.0,
                timeout=120.0,
                on_progress=on_progress,
            )
            print("")
            print("---")
            print(f"Investigation {final_run.status.value}")
            self._show_ui_link(run.run_id)

        except TimeoutError:
            print("")
            print("---")
            print("Investigation still running after timeout.")
            self._show_ui_link(run.run_id)
            print("Check status later with: %dataing status")

    def _show_ui_link(self, run_id: str) -> None:
        """Display a clickable link to the UI.

        Args:
            run_id: The run ID.
        """
        if self._state.client is None:
            return

        base_url = self._state.client.base_url.replace(":8000", ":3000")
        ui_url = f"{base_url}/investigations/{run_id}"

        try:
            from IPython.display import HTML, display

            display(HTML(f'<a href="{ui_url}" target="_blank">View in UI: {ui_url}</a>'))
        except ImportError:
            print(f"View in UI: {ui_url}")

    def _handle_export(self, args: list[str]) -> None:
        """Handle export subcommand - generate markdown incident report.

        Args:
            args: Command arguments.
        """
        parser = argparse.ArgumentParser(prog="%dataing export")
        parser.add_argument(
            "--format", "-f", choices=["markdown", "json"], default="markdown", help="Output format"
        )
        parser.add_argument("--output", "-o", help="Output file path")

        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return

        # Find the last investigation from history
        last_ask = None
        last_stream = None
        for entry in reversed(self._state._history):
            if entry.get("action") == "stream_complete" and last_stream is None:
                last_stream = entry
            if entry.get("action") == "ask" and last_ask is None:
                last_ask = entry
            if last_ask and last_stream:
                break

        if not last_ask:
            print("Error: No investigation found. Run '%dataing ask' first.", file=sys.stderr)
            return

        run_id = last_ask.get("run_id", "unknown")
        question = last_ask.get("question", "Unknown question")
        events = last_stream.get("events", []) if last_stream else []
        status = last_stream.get("status", "unknown") if last_stream else "unknown"

        if parsed.format == "json":
            self._export_json(run_id, question, events, status, parsed.output)
        else:
            self._export_markdown(run_id, question, events, status, parsed.output)

    def _export_markdown(
        self,
        run_id: str,
        question: str,
        events: list[dict[str, Any]],
        status: str,
        output_path: str | None,
    ) -> None:
        """Export investigation as markdown incident report.

        Args:
            run_id: Investigation run ID.
            question: Original question.
            events: List of SSE events.
            status: Final status.
            output_path: Optional output file path.
        """
        from datetime import datetime

        lines = [
            "# Incident Report",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Run ID:** `{run_id}`",
            f"**Status:** {status.upper()}",
            "",
            "## Investigation Question",
            "",
            f"> {question}",
            "",
            "## Timeline",
            "",
        ]

        # Group events by type
        for event in events:
            event_type = event.get("event", "unknown")
            data = event.get("data", {})
            seq = event.get("seq", 0)

            if event_type == "run_started":
                lines.append("### Investigation Started")
                if "goal" in data:
                    lines.append(f"Goal: {data['goal']}")
                lines.append("")

            elif event_type == "run_progress":
                if "hypothesis" in data:
                    lines.append(f"- **Hypothesis:** {data['hypothesis']}")
                elif "message" in data:
                    lines.append(f"- {data['message']}")

            elif event_type == "run_evidence":
                lines.append(f"### Evidence #{seq}")
                if "sql" in data:
                    lines.append("```sql")
                    lines.append(data["sql"])
                    lines.append("```")
                if "result" in data:
                    lines.append(f"Result: {data['result']}")
                if "conclusion" in data:
                    lines.append(f"**Conclusion:** {data['conclusion']}")
                lines.append("")

            elif event_type == "run_completed":
                lines.append("")
                lines.append("### Investigation Completed")
                if "summary" in data:
                    lines.append(data["summary"])
                lines.append("")

            elif event_type == "run_failed":
                lines.append("")
                lines.append("### Investigation Failed")
                if "error" in data:
                    lines.append(f"Error: {data['error']}")
                lines.append("")

        lines.append("---")
        lines.append("*Generated by Dataing Notebook*")

        report = "\n".join(lines)

        if output_path:
            with open(output_path, "w") as f:
                f.write(report)
            print(f"Exported to: {output_path}")
        else:
            # Display in notebook
            try:
                from IPython.display import Markdown, display

                display(Markdown(report))
            except ImportError:
                print(report)

    def _export_json(
        self,
        run_id: str,
        question: str,
        events: list[dict[str, Any]],
        status: str,
        output_path: str | None,
    ) -> None:
        """Export investigation as JSON.

        Args:
            run_id: Investigation run ID.
            question: Original question.
            events: List of SSE events.
            status: Final status.
            output_path: Optional output file path.
        """
        import json
        from datetime import datetime

        data = {
            "generated_at": datetime.now().isoformat(),
            "run_id": run_id,
            "question": question,
            "status": status,
            "events": events,
        }

        json_str = json.dumps(data, indent=2, default=str)

        if output_path:
            with open(output_path, "w") as f:
                f.write(json_str)
            print(f"Exported to: {output_path}")
        else:
            print(json_str)

    def _handle_status(self, args: list[str]) -> None:
        """Handle status subcommand.

        Shows same connection info as the JupyterLab sidebar.

        Args:
            args: Command arguments.
        """
        print("Dataing Notebook Status")
        print("=======================")

        # Client status
        if self._state.client:
            print(f"Backend URL: {self._state.client.base_url}")
            print(f"API Key: {'***' if self._state.client.api_key else 'Not set'}")

            # Show credential mode if known
            credential_mode = getattr(self._state, "_credential_mode", None)
            if credential_mode:
                mode_descriptions = {
                    "keychain": "OS Keychain",
                    "env_var": "Environment Variable",
                    "session": "Session Only",
                }
                mode_display = mode_descriptions.get(credential_mode, credential_mode)
                print(f"Credential Storage: {mode_display}")
        else:
            print("Backend: Not connected")

        # Context status
        if self._state.is_attached and self._state.context:
            ctx = self._state.context
            print("Context: Attached")
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

        # Notify JupyterLab frontend
        self._send_state_update()


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
