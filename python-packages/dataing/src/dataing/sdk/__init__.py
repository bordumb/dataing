"""Dataing SDK for local development and debugging.

This module provides tools for loading and working with investigation
snapshots locally, typically in JupyterLab notebooks.
"""

from dataing.sdk.snapshot import HydratedState, load_snapshot

__all__ = ["load_snapshot", "HydratedState"]
