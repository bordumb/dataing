"""Dataing SDK for local development and debugging.

This module provides tools for loading and working with investigation
snapshots locally, typically in JupyterLab notebooks.

Usage:
    # Load a snapshot directly
    from dataing.sdk import load_snapshot
    state = load_snapshot(snapshot_bytes)

    # Use IPython magic commands (in notebooks)
    %load_ext dataing.sdk.magic
    %dataing hydrate <investigation_id>
"""

from dataing.sdk.snapshot import (
    HydratedState,
    NavigableSchema,
    QueryableLineage,
    SchemaColumn,
    SchemaTable,
    load_snapshot,
)

__all__ = [
    "load_snapshot",
    "HydratedState",
    "NavigableSchema",
    "QueryableLineage",
    "SchemaTable",
    "SchemaColumn",
]
