"""Dataing SDK for local development and debugging.

This module provides tools for loading and working with investigation
snapshots locally, typically in JupyterLab notebooks.

Usage:
    # Load a snapshot directly
    from dataing.sdk import load_snapshot
    state = load_snapshot(snapshot_bytes)

    # Compare two snapshots
    from dataing.sdk import compare_snapshots
    diff = compare_snapshots(state1, state2)

    # Use IPython magic commands (in notebooks)
    %load_ext dataing.sdk.magic
    %dataing hydrate <investigation_id>
    %dataing diff inv_id:start inv_id:complete
"""

from dataing.sdk.diff import (
    DataFrameDiff,
    EvidenceDiff,
    HypothesisDiff,
    SchemaDiff,
    SnapshotDiff,
    SynthesisDiff,
    compare_snapshots,
)
from dataing.sdk.snapshot import (
    HydratedState,
    NavigableSchema,
    QueryableLineage,
    SchemaColumn,
    SchemaTable,
    load_snapshot,
)

__all__ = [
    # Snapshot loading
    "load_snapshot",
    "HydratedState",
    "NavigableSchema",
    "QueryableLineage",
    "SchemaTable",
    "SchemaColumn",
    # Diff comparison
    "compare_snapshots",
    "SnapshotDiff",
    "SchemaDiff",
    "HypothesisDiff",
    "EvidenceDiff",
    "SynthesisDiff",
    "DataFrameDiff",
]
