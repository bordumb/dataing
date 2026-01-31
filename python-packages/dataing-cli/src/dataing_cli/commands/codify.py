"""Codify command - generate regression tests from investigations."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

import typer
from rich.console import Console

from dataing_cli.config import get_client
from dataing_cli.errors import cli_error_handler

if TYPE_CHECKING:
    from dataing.core.codify import DataQualityTest

console = Console()


class OutputFormat(str, Enum):
    """Output format for test generation."""

    gx = "gx"
    dbt = "dbt"
    soda = "soda"
    sql = "sql"


# Create a simple Typer app
app = typer.Typer()


@app.callback(invoke_without_command=True)
def codify(
    ctx: typer.Context,
    investigation_id: Annotated[
        str | None,
        typer.Argument(help="Investigation ID to codify"),
    ] = None,
    format_: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format (gx, dbt, soda, sql)"),
    ] = OutputFormat.sql,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path (stdout if not specified)",
            file_okay=True,
            dir_okay=False,
            writable=True,
            resolve_path=True,
        ),
    ] = None,
    append: Annotated[
        bool,
        typer.Option("--append", help="Append to existing file instead of overwriting"),
    ] = False,
    all_investigations: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Codify all completed investigations (batch mode)",
        ),
    ] = False,
) -> None:
    """Generate regression tests from investigations.

    Extracts testable assertions from investigation synthesis and renders
    them to the specified format (Great Expectations, dbt, Soda, or SQL).

    Examples:
        # Generate SQL test to stdout
        dataing codify inv-abc123

        # Generate dbt test and write to file
        dataing codify inv-abc123 --format dbt --output models/schema.yml

        # Append to existing schema.yml
        dataing codify inv-abc123 --format dbt --output models/schema.yml --append

        # Generate Great Expectations expectation suite
        dataing codify inv-abc123 --format gx --output expectations/suite.json
    """
    if not investigation_id and not all_investigations:
        console.print("[red]Error:[/red] Either investigation_id or --all is required")
        raise typer.Exit(1)

    state = ctx.obj
    client = get_client(
        api_key=state.api_key if state else None,
        base_url=state.base_url if state else None,
    )

    if all_investigations:
        _codify_all(client, format_, output, append, state)
    elif investigation_id:
        _codify_single(client, investigation_id, format_, output, append, state)


@cli_error_handler
def _codify_single(
    client: object,
    investigation_id: str,
    format_: OutputFormat,
    output: Path | None,
    append: bool,
    state: object,
) -> None:
    """Codify a single investigation."""
    from dataing.renderers import get_renderer

    with console.status(f"[bold blue]Fetching investigation {investigation_id}..."):
        investigation = client.get_investigation(investigation_id)  # type: ignore[union-attr]

    if investigation.status != "completed":
        console.print(
            f"[yellow]Warning:[/yellow] Investigation is {investigation.status}, "
            "synthesis may be incomplete"
        )

    synthesis = investigation.synthesis
    if not synthesis:
        console.print("[red]Error:[/red] No synthesis found for this investigation")
        raise typer.Exit(1)

    # Convert synthesis dict to something we can use for extraction
    tests = _extract_tests_from_synthesis_dict(
        synthesis,
        investigation_id=investigation.investigation_id,
    )

    if not tests:
        console.print(
            "[yellow]No testable assertions found.[/yellow] "
            "The investigation may not have identified a clear root cause."
        )
        raise typer.Exit(1)

    # Render tests
    renderer = get_renderer(format_.value)
    rendered = renderer.render_many(tests)

    # Output
    _write_output(rendered, output, append, format_)

    console.print(f"[green]+[/green] Generated {len(tests)} test(s) in {format_.value} format")


def _codify_all(
    client: object,
    format_: OutputFormat,
    output: Path | None,
    append: bool,
    state: object,
) -> None:
    """Codify all completed investigations."""
    console.print("[yellow]--all not yet implemented[/yellow]")
    raise typer.Exit(1)


def _extract_tests_from_synthesis_dict(
    synthesis: dict,
    investigation_id: str,
) -> list[DataQualityTest]:
    """Extract tests from a synthesis dictionary.

    Args:
        synthesis: Synthesis dict from investigation.
        investigation_id: Investigation ID for tagging.

    Returns:
        List of DataQualityTest objects.
    """
    from dataing.agents.models import SynthesisResponse
    from dataing.core.codify import extract_tests_from_synthesis

    # Build a SynthesisResponse from the dict
    try:
        # Ensure we have at least 2 items in causal_chain
        causal_chain = synthesis.get("causal_chain", [])
        if len(causal_chain) < 2:
            causal_chain = ["Issue detected", "Symptom observed"] + causal_chain

        synthesis_response = SynthesisResponse(
            root_cause=synthesis.get("root_cause"),
            confidence=synthesis.get("confidence", 0.0),
            causal_chain=causal_chain,
            estimated_onset=synthesis.get("estimated_onset", "Unknown"),
            affected_scope=synthesis.get("affected_scope", "Unknown scope"),
            supporting_evidence=synthesis.get("supporting_evidence", []),
            contradicting_evidence=synthesis.get("contradicting_evidence", []),
            recommendations=synthesis.get("recommendations", []),
            summary=synthesis.get("summary", ""),
            metadata=synthesis.get("metadata", {}),
        )
    except Exception as e:
        console.print(f"[yellow]Warning:[/yellow] Could not parse synthesis: {e}")
        return []

    # Extract table from metadata or use a default
    table = synthesis.get("metadata", {}).get("dataset", "unknown_table")
    if "." in table:
        # Take just the table name if fully qualified
        table = table.split(".")[-1]

    return extract_tests_from_synthesis(
        synthesis=synthesis_response,
        investigation_id=UUID(investigation_id) if investigation_id else UUID(int=0),
        table=table,
    )


def _write_output(
    content: str,
    output: Path | None,
    append: bool,
    format_: OutputFormat,
) -> None:
    """Write rendered content to file or stdout.

    Args:
        content: Rendered test content.
        output: Output file path (None for stdout).
        append: Whether to append to existing file.
        format_: Output format (for append handling).
    """
    if output is None:
        # Write to stdout
        print(content)
        return

    if append and output.exists():
        existing = output.read_text()

        # Format-specific append logic
        if format_ == OutputFormat.dbt:
            # For dbt, we need to merge schema.yml properly
            content = _merge_dbt_schema(existing, content)
        elif format_ == OutputFormat.soda:
            # For Soda, just append checks
            content = existing + "\n" + content
        elif format_ == OutputFormat.gx:
            # For GX, merge expectation suites
            content = _merge_gx_suite(existing, content)
        else:
            # For SQL, just append
            content = existing + "\n\n" + content

    output.write_text(content)


def _merge_dbt_schema(existing: str, new: str) -> str:
    """Merge new dbt schema content into existing schema.yml.

    Args:
        existing: Existing schema.yml content.
        new: New schema content to merge.

    Returns:
        Merged schema.yml content.
    """
    import yaml  # type: ignore[import-untyped]

    try:
        existing_schema = yaml.safe_load(existing) or {}
        new_schema = yaml.safe_load(new) or {}

        # Merge models
        existing_models = {m["name"]: m for m in existing_schema.get("models", [])}
        for model in new_schema.get("models", []):
            model_name = model["name"]
            if model_name in existing_models:
                # Merge columns and tests
                existing_model = existing_models[model_name]
                existing_columns = {c["name"]: c for c in existing_model.get("columns", [])}
                for col in model.get("columns", []):
                    col_name = col["name"]
                    if col_name in existing_columns:
                        # Append tests to existing column
                        existing_tests = existing_columns[col_name].get("tests", [])
                        new_tests = col.get("tests", [])
                        existing_columns[col_name]["tests"] = existing_tests + new_tests
                    else:
                        existing_columns[col_name] = col
                existing_model["columns"] = list(existing_columns.values())

                # Merge table-level tests
                if "tests" in model:
                    existing_tests = existing_model.get("tests", [])
                    existing_model["tests"] = existing_tests + model["tests"]
            else:
                existing_models[model_name] = model

        existing_schema["models"] = list(existing_models.values())
        result: str = yaml.dump(existing_schema, default_flow_style=False, sort_keys=False)
        return result

    except Exception:
        # If merge fails, just append
        return existing + "\n" + new


def _merge_gx_suite(existing: str, new: str) -> str:
    """Merge new GX expectation suite into existing suite.

    Args:
        existing: Existing expectation suite JSON.
        new: New expectation suite JSON to merge.

    Returns:
        Merged expectation suite JSON.
    """
    import json

    try:
        existing_suite = json.loads(existing)
        new_suite = json.loads(new)

        # Merge expectations
        existing_expectations = existing_suite.get("expectations", [])
        new_expectations = new_suite.get("expectations", [])
        existing_suite["expectations"] = existing_expectations + new_expectations

        # Merge meta
        existing_meta = existing_suite.get("meta", {})
        new_meta = new_suite.get("meta", {})
        existing_meta.update(new_meta)
        existing_suite["meta"] = existing_meta

        return json.dumps(existing_suite, indent=2)

    except Exception:
        # If merge fails, just return new
        return new
