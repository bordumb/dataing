"""Interactive lineage graph visualization using ipycytoscape.

This module provides functions to render lineage data as an interactive
DAG in Jupyter notebooks, with fallback to ASCII for non-widget environments.
"""

from __future__ import annotations

from collections import deque
from typing import Any

# Node type -> visual style mapping
NODE_STYLES: dict[str, dict[str, Any]] = {
    "table": {"background-color": "#3b82f6", "shape": "round-rectangle"},
    "view": {"background-color": "#10b981", "shape": "round-rectangle"},
    "source": {"background-color": "#f59e0b", "shape": "ellipse"},
    "job": {"background-color": "#8b5cf6", "shape": "diamond"},
}

ROOT_STYLE: dict[str, Any] = {
    "background-color": "#ef4444",
    "border-width": 3,
    "border-color": "#b91c1c",
}


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
        return shell.__class__.__name__ == "ZMQInteractiveShell"
    except ImportError:
        return False


def _filter_by_depth_and_direction(
    root: str,
    edges: list[dict[str, Any]],
    *,
    depth: int,
    direction: str,
) -> set[str]:
    """BFS from root to find reachable nodes within depth hops.

    Args:
        root: The root node identifier.
        edges: List of edge dicts with 'source' and 'target' keys.
        depth: Maximum hops from root.
        direction: 'upstream', 'downstream', or 'both'.

    Returns:
        Set of reachable node identifiers (always includes root).
    """
    # Build adjacency lists
    downstream_adj: dict[str, list[str]] = {}
    upstream_adj: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        downstream_adj.setdefault(src, []).append(tgt)
        upstream_adj.setdefault(tgt, []).append(src)

    reachable: set[str] = {root}
    queue: deque[tuple[str, int]] = deque([(root, 0)])

    while queue:
        node, dist = queue.popleft()
        if dist >= depth:
            continue

        neighbors: list[str] = []
        if direction in ("downstream", "both"):
            neighbors.extend(downstream_adj.get(node, []))
        if direction in ("upstream", "both"):
            neighbors.extend(upstream_adj.get(node, []))

        for neighbor in neighbors:
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append((neighbor, dist + 1))

    return reachable


def lineage_to_cytoscape_elements(
    lineage_data: dict[str, Any],
    *,
    depth: int = 2,
    direction: str = "both",
) -> list[dict[str, Any]]:
    """Convert lineage API response to cytoscape elements list.

    Args:
        lineage_data: Dict with keys root, datasets, edges, jobs.
        depth: Maximum edge hops from root to include.
        direction: 'upstream', 'downstream', or 'both'.

    Returns:
        List of cytoscape element dicts (nodes + edges).
    """
    root = lineage_data.get("root", "")
    datasets: dict[str, Any] = lineage_data.get("datasets", {})
    edges: list[dict[str, Any]] = lineage_data.get("edges", [])
    jobs: dict[str, Any] = lineage_data.get("jobs", {})

    if not root and not edges:
        return []

    # Determine which nodes are reachable
    reachable = _filter_by_depth_and_direction(root, edges, depth=depth, direction=direction)

    elements: list[dict[str, Any]] = []

    # Collect all node IDs from edges + datasets + jobs + root
    all_node_ids: set[str] = {root} if root else set()
    for edge in edges:
        all_node_ids.add(edge.get("source", ""))
        all_node_ids.add(edge.get("target", ""))
    for dataset_id in datasets:
        all_node_ids.add(dataset_id)
    for job_id in jobs:
        all_node_ids.add(job_id)
    all_node_ids.discard("")

    # Build nodes
    for node_id in sorted(all_node_ids):
        if node_id not in reachable:
            continue

        is_job = node_id in jobs
        is_root = node_id == root

        # Determine node type for styling
        if is_job:
            node_type = "job"
        elif node_id in datasets:
            dataset_info = datasets[node_id]
            node_type = (
                dataset_info.get("type", "table") if isinstance(dataset_info, dict) else "table"
            )
        else:
            node_type = "table"

        # Short label: use last segment of qualified name
        label = node_id.rsplit(".", 1)[-1] if "." in node_id else node_id

        node_data: dict[str, Any] = {
            "id": node_id,
            "label": label,
            "node_type": node_type,
            "is_root": is_root,
        }

        # Attach dataset details for click handlers
        if node_id in datasets and isinstance(datasets[node_id], dict):
            node_data["details"] = datasets[node_id]

        classes = node_type
        if is_root:
            classes += " root"

        elements.append(
            {
                "data": node_data,
                "classes": classes,
            }
        )

    # Build edges (only between reachable nodes)
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in reachable and tgt in reachable:
            edge_type = edge.get("edge_type", "transforms")
            elements.append(
                {
                    "data": {
                        "source": src,
                        "target": tgt,
                        "label": edge_type,
                    },
                }
            )

    return elements


def _build_widget(elements: list[dict[str, Any]]) -> Any:
    """Build an ipycytoscape widget from elements with dagre layout.

    Args:
        elements: Cytoscape element dicts.

    Returns:
        ipycytoscape.CytoscapeWidget instance.
    """
    cyto = _get_cytoscape_widget()
    widget = cyto.CytoscapeWidget()
    widget.graph.add_graph_from_json({"elements": elements})

    widget.set_layout(name="dagre", rankDir="TB", nodeSep=60, rankSep=80)

    # Build per-type node style selectors
    type_styles = []
    for node_type, style in NODE_STYLES.items():
        type_styles.append(
            {
                "selector": f"node.{node_type}",
                "style": style,
            }
        )

    widget.set_style(
        [
            {
                "selector": "node",
                "style": {
                    "label": "data(label)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "font-size": "12px",
                    "width": "label",
                    "height": 40,
                    "padding": "10px",
                    "color": "#ffffff",
                    "font-weight": "bold",
                    "background-color": "#64748b",
                    "shape": "round-rectangle",
                },
            },
            {
                "selector": "edge",
                "style": {
                    "curve-style": "bezier",
                    "target-arrow-shape": "triangle",
                    "arrow-scale": 1.2,
                    "line-color": "#94a3b8",
                    "target-arrow-color": "#94a3b8",
                    "width": 2,
                    "label": "data(label)",
                    "font-size": "10px",
                    "color": "#64748b",
                    "text-rotation": "autorotate",
                },
            },
            {
                "selector": "node.root",
                "style": ROOT_STYLE,
            },
            *type_styles,
        ]
    )

    return widget


def _render_ascii_fallback(
    lineage_data: dict[str, Any],
    *,
    depth: int = 2,
    direction: str = "both",
) -> None:
    """Render lineage as plain ASCII text for non-widget environments.

    Args:
        lineage_data: Lineage API response dict.
        depth: Max traversal depth to display.
        direction: One of 'upstream', 'downstream', 'both'.
    """
    root = lineage_data.get("root", "Unknown")
    edges: list[dict[str, Any]] = lineage_data.get("edges", [])

    reachable = _filter_by_depth_and_direction(root, edges, depth=depth, direction=direction)

    print(f"Lineage Graph (root: {root}, depth: {depth}, direction: {direction})")
    print("=" * 60)

    if not edges:
        print(f"  {root} (no edges)")
        return

    for edge in edges:
        src = edge.get("source", "?")
        tgt = edge.get("target", "?")
        if src in reachable and tgt in reachable:
            edge_type = edge.get("edge_type", "transforms")
            print(f"  {src} --[{edge_type}]--> {tgt}")


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
    if not lineage_data:
        print("No lineage data available.")
        return None

    if not is_widget_environment():
        _render_ascii_fallback(lineage_data, depth=depth, direction=direction)
        return None

    elements = lineage_to_cytoscape_elements(lineage_data, depth=depth, direction=direction)
    if not elements:
        print("No lineage elements to display.")
        return None

    return _build_widget(elements)
