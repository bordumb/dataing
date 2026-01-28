"""Interactive lineage graph visualization using ipycytoscape.

This module provides functions to render lineage data as an interactive
DAG in Jupyter notebooks, with fallback to ASCII for non-widget environments.
"""

from __future__ import annotations

from typing import Any


def _get_cytoscape_widget() -> Any:
    """Lazy-import ipycytoscape, raising ImportError if unavailable.

    Returns:
        The ipycytoscape module.

    Raises:
        ImportError: If ipycytoscape is not installed.
    """
    try:
        import ipycytoscape  # type: ignore[import-untyped]

        return ipycytoscape
    except ImportError as e:
        raise ImportError(
            "ipycytoscape is required for interactive lineage graphs. "
            "Install it with: pip install 'dataing-notebook[graph]'"
        ) from e


def is_widget_environment() -> bool:
    """Detect whether the current environment supports ipywidgets.

    Checks for ZMQInteractiveShell (JupyterLab/Notebook) and verifies
    that ipywidgets comm infrastructure is available.

    Returns:
        True if widgets can render, False otherwise.
    """
    try:
        from IPython import get_ipython  # type: ignore[import-untyped]

        shell = get_ipython()
        if shell is None:
            return False
        # Only ZMQ shells (Jupyter) support widgets; terminal does not
        return shell.__class__.__name__ == "ZMQInteractiveShell"
    except ImportError:
        return False


def render_lineage_graph(
    lineage_data: dict[str, Any],
    *,
    depth: int = 2,
    direction: str = "both",
) -> Any:
    """Render lineage data as an interactive cytoscape graph or ASCII fallback.

    Args:
        lineage_data: Lineage API response dict with root, datasets, edges, jobs.
        depth: Max traversal depth to display.
        direction: One of 'upstream', 'downstream', 'both'.

    Returns:
        ipycytoscape CytoscapeWidget if in a widget environment, None otherwise
        (ASCII printed to stdout as fallback).
    """
    ...
