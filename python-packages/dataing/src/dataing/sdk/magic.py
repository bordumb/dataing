"""IPython magic commands for Dataing notebook integration.

This module provides magic commands for interacting with Dataing
from within JupyterLab notebooks.

Usage:
    %load_ext dataing.sdk.magic

    # Hydrate investigation state into notebook namespace
    %dataing hydrate <investigation_id> [--checkpoint <checkpoint>]

    # List recent investigations
    %dataing list

    # Show help
    %dataing help

Note: Requires IPython to be installed. Install with: pip install ipython
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# Stub base class for when IPython is not available
class _StubMagics:
    """Stub Magics base class when IPython not available."""

    def __init__(self, shell: Any = None) -> None:
        """Initialize magics."""
        self.shell = shell


def _stub_magics_class(cls: F) -> F:
    """Stub decorator when IPython not available."""
    return cls


def _stub_line_magic(func: F) -> F:
    """Stub decorator when IPython not available."""
    return func


def _stub_magic_arguments() -> Callable[[F], F]:
    """Stub decorator when IPython not available."""

    def decorator(func: F) -> F:
        return func

    return decorator


def _stub_argument(*args: Any, **kwargs: Any) -> Callable[[F], F]:
    """Stub decorator when IPython not available."""

    def decorator(func: F) -> F:
        return func

    return decorator


def _stub_parse_argstring(func: Any, line: str) -> argparse.Namespace:
    """Stub function when IPython not available."""
    # Parse manually for basic compatibility
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--checkpoint", "-c", default="complete")
    parser.add_argument("--namespace", "-n", default="dataing")
    parser.add_argument("--overwrite", "-o", action="store_true")
    return parser.parse_args(line.split())


# IPython is optional - only available in notebook environments
IPYTHON_AVAILABLE = False
BaseMagics: type = _StubMagics

# Initialize with stubs
magics_class: Callable[[F], F] = _stub_magics_class
line_magic: Callable[[F], F] = _stub_line_magic
magic_arguments: Callable[[], Callable[[F], F]] = _stub_magic_arguments
argument: Callable[..., Callable[[F], F]] = _stub_argument
parse_argstring: Callable[[Any, str], Any] = _stub_parse_argstring

try:
    from IPython.core.magic import Magics as IPythonMagics
    from IPython.core.magic import line_magic as _ipython_line_magic
    from IPython.core.magic import magics_class as _ipython_magics_class
    from IPython.core.magic_arguments import argument as _ipython_argument
    from IPython.core.magic_arguments import magic_arguments as _ipython_magic_arguments
    from IPython.core.magic_arguments import parse_argstring as _ipython_parse_argstring

    IPYTHON_AVAILABLE = True
    BaseMagics = IPythonMagics
    magics_class = _ipython_magics_class  # type: ignore[assignment]
    line_magic = _ipython_line_magic  # type: ignore[assignment]
    magic_arguments = _ipython_magic_arguments  # type: ignore[assignment]
    argument = _ipython_argument  # type: ignore[assignment]
    parse_argstring = _ipython_parse_argstring  # type: ignore[assignment]
except ImportError:
    pass


def _get_api_client() -> tuple[str, dict[str, str]]:
    """Get API base URL and headers from environment.

    Returns:
        Tuple of (base_url, headers dict).

    Raises:
        RuntimeError: If not connected to Dataing backend.
    """
    base_url = os.environ.get("DATAING_API_URL", "")
    api_key = os.environ.get("DATAING_API_KEY", "")

    if not base_url:
        raise RuntimeError(
            "Not connected to Dataing backend. "
            "Use the connection wizard in the sidebar or set DATAING_API_URL."
        )

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    return base_url.rstrip("/"), headers


def _fetch_snapshot(
    investigation_id: str,
    checkpoint: str = "complete",
) -> bytes:
    """Fetch snapshot from API.

    Args:
        investigation_id: UUID of the investigation.
        checkpoint: Checkpoint to fetch (default: complete).

    Returns:
        Raw snapshot bytes.

    Raises:
        RuntimeError: If fetch fails.
    """
    base_url, headers = _get_api_client()
    url = f"{base_url}/api/v1/investigations/{investigation_id}/snapshots/{checkpoint}"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result: bytes = response.read()
            return result
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(
                f"Snapshot not found for investigation {investigation_id} "
                f"at checkpoint '{checkpoint}'."
            ) from e
        raise RuntimeError(f"Failed to fetch snapshot: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to Dataing API: {e.reason}") from e


def _list_investigations(limit: int = 10) -> list[dict[str, Any]]:
    """List recent investigations from API.

    Args:
        limit: Maximum number of investigations to return.

    Returns:
        List of investigation dicts.

    Raises:
        RuntimeError: If fetch fails.
    """
    base_url, headers = _get_api_client()
    url = f"{base_url}/api/v1/investigations"

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data[:limit] if isinstance(data, list) else []
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Failed to list investigations: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to Dataing API: {e.reason}") from e


@magics_class
class DataingMagics(BaseMagics):  # type: ignore[misc]
    """IPython magic commands for Dataing integration."""

    @line_magic
    @magic_arguments()
    @argument("command", help="Command to execute (hydrate, list, help)")
    @argument("args", nargs="*", help="Command arguments")
    @argument(
        "--checkpoint",
        "-c",
        default="complete",
        help="Checkpoint to hydrate (start, hypothesis_generated, complete, failed)",
    )
    @argument(
        "--namespace",
        "-n",
        default="dataing",
        help="Variable namespace prefix (default: dataing)",
    )
    @argument(
        "--overwrite",
        "-o",
        action="store_true",
        help="Overwrite existing variables without prompting",
    )
    def dataing(self, line: str) -> None:
        """Execute Dataing magic commands.

        Usage:
            %dataing hydrate <investigation_id> [--checkpoint <checkpoint>]
            %dataing diff <spec1> <spec2>
            %dataing list
            %dataing help
        """
        args = parse_argstring(self.dataing, line)
        command = args.command.lower()

        if command == "hydrate":
            self._hydrate(args)
        elif command == "diff":
            self._diff(args)
        elif command == "list":
            self._list_investigations(args)
        elif command == "help":
            self._show_help()
        else:
            print(f"Unknown command: {command}")
            print("Use '%dataing help' for available commands.")

    def _hydrate(self, args: Any) -> None:
        """Hydrate investigation state into notebook namespace.

        Args:
            args: Parsed magic arguments.
        """
        from dataing.sdk.snapshot import load_snapshot

        if not args.args:
            print("Error: investigation_id required")
            print("Usage: %dataing hydrate <investigation_id> [--checkpoint <checkpoint>]")
            return

        investigation_id = args.args[0]
        checkpoint = args.checkpoint
        namespace = args.namespace
        overwrite = args.overwrite

        # Validate investigation_id format (UUID)
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        if not re.match(uuid_pattern, investigation_id.lower()):
            print(f"Error: Invalid investigation ID format: {investigation_id}")
            print("Expected UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
            return

        print(f"Hydrating investigation {investigation_id} from checkpoint '{checkpoint}'...")

        try:
            # Fetch snapshot from API
            print("  Downloading snapshot...")
            snapshot_bytes = _fetch_snapshot(investigation_id, checkpoint)
            print(f"  Downloaded {len(snapshot_bytes):,} bytes")

            # Deserialize snapshot
            print("  Deserializing...")
            state = load_snapshot(snapshot_bytes, lazy_dataframes=True)

            # Check for existing variables
            shell = self.shell
            existing_vars = []
            var_names = self._get_variable_names(state, namespace)

            for var_name in var_names:
                if var_name in shell.user_ns and not overwrite:
                    existing_vars.append(var_name)

            if existing_vars and not overwrite:
                existing = ", ".join(existing_vars)
                print(f"\nWarning: Variables already exist: {existing}")
                print("Use --overwrite to replace, or --namespace for a different prefix.")
                return

            # Inject variables into kernel namespace
            print("  Injecting variables into kernel...")
            injected = self._inject_variables(state, namespace)

            print(f"\nHydrated investigation {investigation_id}")
            print(f"  Checkpoint: {state.checkpoint}")
            print(f"  Hypotheses: {len(state.hypotheses)}")
            print(f"  Evidence: {len(state.evidence)}")
            print("\nVariables available:")
            for var_name, var_type in injected:
                print(f"  {var_name}: {var_type}")

            if state.synthesis:
                print(f"\nRoot cause: {state.synthesis.get('root_cause', 'N/A')}")
                print(f"Confidence: {state.synthesis.get('confidence', 'N/A')}")

        except RuntimeError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Error hydrating snapshot: {e}")
            logger.exception("Failed to hydrate snapshot")

    def _diff(self, args: Any) -> None:
        """Compare two snapshots.

        Args:
            args: Parsed magic arguments containing snapshot specs.

        Format:
            %dataing diff inv_id:checkpoint1 inv_id:checkpoint2
            %dataing diff inv_id:start inv_id:complete
        """
        from dataing.sdk.diff import compare_snapshots
        from dataing.sdk.snapshot import load_snapshot

        if len(args.args) < 2:
            print("Error: Two snapshot specs required")
            print("Usage: %dataing diff <inv_id:checkpoint> <inv_id:checkpoint>")
            print("Example: %dataing diff abc123:start abc123:complete")
            return

        spec1 = args.args[0]
        spec2 = args.args[1]

        # Parse specs (format: investigation_id:checkpoint or just investigation_id)
        def parse_spec(spec: str) -> tuple[str, str]:
            if ":" in spec:
                parts = spec.split(":", 1)
                return parts[0], parts[1]
            return spec, "complete"

        inv1, checkpoint1 = parse_spec(spec1)
        inv2, checkpoint2 = parse_spec(spec2)

        # Validate UUIDs
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        for inv_id, name in [(inv1, "first"), (inv2, "second")]:
            if not re.match(uuid_pattern, inv_id.lower()):
                print(f"Error: Invalid {name} investigation ID: {inv_id}")
                return

        print(f"Comparing {inv1}:{checkpoint1} with {inv2}:{checkpoint2}...")

        try:
            # Fetch both snapshots
            print("  Downloading first snapshot...")
            bytes1 = _fetch_snapshot(inv1, checkpoint1)
            print("  Downloading second snapshot...")
            bytes2 = _fetch_snapshot(inv2, checkpoint2)

            # Deserialize
            print("  Deserializing snapshots...")
            state1 = load_snapshot(bytes1, lazy_dataframes=False)
            state2 = load_snapshot(bytes2, lazy_dataframes=False)

            # Compare
            print("  Computing diff...")
            diff = compare_snapshots(state1, state2)

            # Display result
            print("\n" + "=" * 60)
            print(diff.summary())
            print("=" * 60)

            # Store diff in namespace for further exploration
            shell = self.shell
            shell.user_ns["dataing_diff"] = diff
            print("\nDiff object stored as 'dataing_diff'")
            print("  View as HTML: display(dataing_diff)")
            print("  Export as markdown: print(dataing_diff.to_markdown())")

        except RuntimeError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Error comparing snapshots: {e}")
            logger.exception("Failed to compare snapshots")

    def _get_variable_names(self, state: Any, namespace: str) -> list[str]:
        """Get list of variable names that would be injected.

        Args:
            state: HydratedState object.
            namespace: Variable namespace prefix.

        Returns:
            List of variable names.
        """
        names = [
            f"{namespace}_alert",
            f"{namespace}_hypotheses",
            f"{namespace}_evidence",
            f"{namespace}_synthesis",
            f"{namespace}_schema",
            f"{namespace}_lineage",
            f"{namespace}_state",
        ]

        # Add DataFrame names
        for table_name in state.dataframes.keys():
            names.append(f"df_{table_name}")

        return names

    def _inject_variables(self, state: Any, namespace: str) -> list[tuple[str, str]]:
        """Inject variables into kernel namespace.

        Args:
            state: HydratedState object.
            namespace: Variable namespace prefix.

        Returns:
            List of (name, type) tuples for injected variables.
        """
        shell = self.shell
        injected: list[tuple[str, str]] = []

        # Core state variables
        variables = {
            f"{namespace}_alert": state.alert,
            f"{namespace}_hypotheses": state.hypotheses,
            f"{namespace}_evidence": state.evidence,
            f"{namespace}_synthesis": state.synthesis,
            f"{namespace}_schema": state.schema,
            f"{namespace}_lineage": state.lineage,
            f"{namespace}_state": state,  # Full state object
        }

        for name, value in variables.items():
            shell.user_ns[name] = value
            type_name = type(value).__name__ if value is not None else "None"
            injected.append((name, type_name))

        # DataFrames (with df_ prefix for easy access)
        for table_name in state.dataframes.keys():
            df = state.dataframes.get(table_name)
            var_name = f"df_{table_name}"
            shell.user_ns[var_name] = df
            type_name = type(df).__name__ if df is not None else "None"
            injected.append((var_name, type_name))

        return injected

    def _list_investigations(self, args: Any) -> None:
        """List recent investigations.

        Args:
            args: Parsed magic arguments.
        """
        print("Recent investigations:")
        print("-" * 80)

        try:
            investigations = _list_investigations(limit=10)

            if not investigations:
                print("No investigations found.")
                return

            for inv in investigations:
                inv_id = inv.get("investigation_id", "unknown")
                status = inv.get("status", "unknown")
                created = inv.get("created_at", "unknown")
                dataset = inv.get("dataset_id", "unknown")

                # Truncate for display
                if len(created) > 19:
                    created = created[:19]

                print(f"  {inv_id}  {status:<12}  {created}  {dataset}")

            print("-" * 80)
            print("Use '%dataing hydrate <investigation_id>' to load state.")

        except RuntimeError as e:
            print(f"Error: {e}")

    def _show_help(self) -> None:
        """Show help message."""
        help_text = """
Dataing Magic Commands
======================

Hydrate investigation state:
    %dataing hydrate <investigation_id> [options]

    Options:
        --checkpoint, -c    Checkpoint to load (default: complete)
                            Values: start, hypothesis_generated, complete, failed
        --namespace, -n     Variable prefix (default: dataing)
        --overwrite, -o     Overwrite existing variables without prompting

    Example:
        %dataing hydrate abc123-def456-... --checkpoint hypothesis_generated

    This loads the investigation state and injects variables:
        dataing_alert       - The anomaly alert that triggered the investigation
        dataing_hypotheses  - List of generated hypotheses
        dataing_evidence    - List of collected evidence
        dataing_synthesis   - Final synthesis result
        dataing_schema      - NavigableSchema for exploring table structure
        dataing_lineage     - QueryableLineage for data dependencies
        dataing_state       - Full HydratedState object
        df_<table>          - pandas DataFrames for each sampled table

Compare two snapshots:
    %dataing diff <spec1> <spec2>

    Spec format: <investigation_id>:<checkpoint>
    Checkpoints: start, hypothesis_generated, complete, failed

    Examples:
        %dataing diff abc123:start abc123:complete
        %dataing diff abc123:hypothesis_generated abc123:complete

    Output includes changes to:
        - Schema (added/removed tables, columns, type changes)
        - Hypotheses (added/removed, status changes)
        - Evidence (added/removed)
        - Synthesis (root cause, confidence)
        - DataFrames (row counts, value changes)

    The diff object is stored as 'dataing_diff' for further exploration.

List recent investigations:
    %dataing list

Show this help:
    %dataing help
"""
        print(help_text)


def load_ipython_extension(ipython: Any) -> None:
    """Load the extension in IPython.

    Args:
        ipython: IPython interactive shell instance.
    """
    ipython.register_magics(DataingMagics)
    print("Dataing magic commands loaded. Use '%dataing help' for usage.")


def unload_ipython_extension(ipython: Any) -> None:
    """Unload the extension from IPython.

    Args:
        ipython: IPython interactive shell instance.
    """
    # IPython handles magic unregistration automatically
    pass
