"""Interactive lineage graph visualization using ipycytoscape.

This module provides functions to render lineage data as an interactive
DAG in Jupyter notebooks, with fallback to ASCII for non-widget environments.
"""

from __future__ import annotations

from collections import deque
from html import escape
from pathlib import Path
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


def _get_ipywidgets() -> Any:
    """Lazy-import ipywidgets.

    Returns:
        The ipywidgets module.

    Raises:
        ImportError: If ipywidgets is not installed.
    """
    try:
        import ipywidgets  # type: ignore[import-untyped]

        return ipywidgets
    except ImportError as e:
        raise ImportError(
            "ipywidgets is required for interactive lineage graphs. "
            "Install it with: pip install ipywidgets"
        ) from e


def _render_dataset_details(dataset_id: str, dataset: dict[str, Any]) -> str:
    """Render dataset metadata as HTML for the details panel.

    Args:
        dataset_id: Dataset identifier.
        dataset: Dataset metadata dict from the API response.

    Returns:
        HTML string with escaped content.
    """
    name = escape(str(dataset_id))
    platform = escape(str(dataset.get("platform", "Unknown")))
    dtype = escape(str(dataset.get("type", "table")))
    description = escape(str(dataset.get("description", "")))

    html = f"""
    <div style="font-family: sans-serif; font-size: 13px;">
      <h4 style="margin: 0 0 8px 0; color: #1e293b;">{name}</h4>
      <table style="border-collapse: collapse; width: 100%;">
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Platform</td>
            <td>{platform}</td></tr>
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Type</td>
            <td>{dtype}</td></tr>
    """

    if description:
        html += f"""
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Description</td>
            <td>{description}</td></tr>
        """

    owners = dataset.get("owners", [])
    if owners:
        owners_str = escape(", ".join(str(o) for o in owners))
        html += f"""
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Owners</td>
            <td>{owners_str}</td></tr>
        """

    tags = dataset.get("tags", [])
    if tags:
        tags_html = " ".join(
            f'<span style="background: #e2e8f0; padding: 1px 6px; border-radius: 4px;'
            f' font-size: 11px;">{escape(str(t))}</span>'
            for t in tags
        )
        html += f"""
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Tags</td>
            <td>{tags_html}</td></tr>
        """

    schema = dataset.get("schema", [])
    if schema:
        cols_html = ", ".join(
            f"<code>{escape(str(col.get('name', '?')))}</code>" for col in schema[:10]
        )
        if len(schema) > 10:
            cols_html += f" ... +{len(schema) - 10} more"
        html += f"""
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Schema</td>
            <td>{cols_html}</td></tr>
        """

    html += "</table></div>"
    return html


def _render_job_details(job_id: str, job: dict[str, Any]) -> str:
    """Render job metadata as HTML for the details panel.

    Args:
        job_id: Job identifier.
        job: Job metadata dict from the API response.

    Returns:
        HTML string with escaped content.
    """
    name = escape(str(job_id))
    jtype = escape(str(job.get("type", "Unknown")))

    html = f"""
    <div style="font-family: sans-serif; font-size: 13px;">
      <h4 style="margin: 0 0 8px 0; color: #1e293b;">{name}</h4>
      <table style="border-collapse: collapse; width: 100%;">
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Type</td>
            <td>{jtype}</td></tr>
    """

    inputs = job.get("inputs", [])
    if inputs:
        inputs_str = escape(", ".join(str(i) for i in inputs))
        html += f"""
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Inputs</td>
            <td>{inputs_str}</td></tr>
        """

    outputs = job.get("outputs", [])
    if outputs:
        outputs_str = escape(", ".join(str(o) for o in outputs))
        html += f"""
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Outputs</td>
            <td>{outputs_str}</td></tr>
        """

    source_url = job.get("source_url", "")
    if source_url:
        safe_url = escape(str(source_url))
        html += f"""
        <tr><td style="color: #6b7280; padding: 2px 8px 2px 0;">Source</td>
            <td><a href="{safe_url}" target="_blank">{safe_url}</a></td></tr>
        """

    html += "</table></div>"
    return html


def _create_details_panel() -> Any:
    """Create an HTML widget to display node details.

    Returns:
        ipywidgets.HTML widget for rendering details.
    """
    widgets = _get_ipywidgets()
    panel = widgets.HTML(
        value="<p style='color: #6b7280; font-family: sans-serif;'>Click a node to see details</p>"
    )
    panel.layout = widgets.Layout(
        border="1px solid #e5e7eb",
        padding="12px",
        margin="8px 0",
        min_height="80px",
    )
    return panel


def _on_node_click(
    node: dict[str, Any],
    details_panel: Any,
    lineage_data: dict[str, Any],
) -> None:
    """Handle node click event and update details panel.

    Args:
        node: Cytoscape node event dict with 'data' key.
        details_panel: ipywidgets.HTML widget to update.
        lineage_data: Full lineage data for lookups.
    """
    data = node.get("data", {})
    node_id = data.get("id", "")
    node_type = data.get("node_type", "table")

    if node_type == "job":
        job = lineage_data.get("jobs", {}).get(node_id, {})
        details_panel.value = _render_job_details(node_id, job)
    else:
        dataset = lineage_data.get("datasets", {}).get(node_id, {})
        details_panel.value = _render_dataset_details(node_id, dataset)


def _render_ascii_fallback(
    lineage_data: dict[str, Any],
    *,
    depth: int = 2,
    direction: str = "both",
) -> None:
    """Render lineage as ASCII tree with box-drawing characters.

    Produces output like::

        Lineage Graph (depth=2, direction=both)
        ==================================================
        +-- orders [table] (root)
            +-- raw_orders [source]
            +-- raw_customers [source]

    Args:
        lineage_data: Lineage API response dict.
        depth: Max traversal depth to display.
        direction: One of 'upstream', 'downstream', 'both'.
    """
    root = lineage_data.get("root", "Unknown")
    datasets: dict[str, Any] = lineage_data.get("datasets", {})
    edges: list[dict[str, Any]] = lineage_data.get("edges", [])

    print(f"Lineage Graph (depth={depth}, direction={direction})")
    print("=" * 50)

    if not edges:
        print(f"+-- {root} (root, no edges)")
        return

    # Build adjacency for tree display
    children: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if direction == "upstream":
            children.setdefault(tgt, []).append(src)
        elif direction == "downstream":
            children.setdefault(src, []).append(tgt)
        else:
            children.setdefault(src, []).append(tgt)
            children.setdefault(tgt, []).append(src)

    visited: set[str] = set()

    def _print_node(node: str, prefix: str, is_last: bool, current_depth: int) -> None:
        if current_depth > depth or node in visited:
            return
        visited.add(node)

        connector = "+-- "
        ds_info = datasets.get(node, {})
        ds_type = ds_info.get("type", "") if isinstance(ds_info, dict) else ""
        type_label = f" [{ds_type}]" if ds_type else ""
        root_label = " (root)" if node == root else ""
        label = node.rsplit(".", 1)[-1] if "." in node else node

        print(f"{prefix}{connector}{label}{type_label}{root_label}")

        child_nodes = children.get(node, [])
        for i, child in enumerate(child_nodes):
            is_child_last = i == len(child_nodes) - 1
            child_prefix = prefix + ("    " if is_last else "|   ")
            _print_node(child, child_prefix, is_child_last, current_depth + 1)

    _print_node(root, "", True, 0)


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

    widgets = _get_ipywidgets()
    graph_widget = _build_widget(elements)
    details_panel = _create_details_panel()

    def on_click(node: dict[str, Any]) -> None:
        """Handle node click."""
        _on_node_click(node, details_panel, lineage_data)

    graph_widget.on("node", "click", on_click)

    return widgets.VBox([graph_widget, details_panel])


def export_lineage_graph(
    lineage_data: dict[str, Any],
    output_path: str,
    *,
    fmt: str = "png",
    depth: int = 2,
    direction: str = "both",
) -> str:
    """Export lineage graph to PNG or SVG file.

    Args:
        lineage_data: Lineage API response dict.
        output_path: File path to write (e.g., "lineage.png").
        fmt: Export format, either "png" or "svg".
        depth: Max traversal depth.
        direction: 'upstream', 'downstream', or 'both'.

    Returns:
        Absolute path of the written file.

    Raises:
        ImportError: If ipycytoscape is not installed.
        ValueError: If fmt is not 'png' or 'svg'.
    """
    if fmt not in ("png", "svg"):
        raise ValueError(f"Unsupported format: {fmt!r}. Use 'png' or 'svg'.")

    elements = lineage_to_cytoscape_elements(lineage_data, depth=depth, direction=direction)
    widget = _build_widget(elements)

    if fmt == "png":
        data: bytes | str = widget.get_png()
        mode = "wb"
    else:
        data = widget.get_svg()
        mode = "w"

    with open(output_path, mode) as f:
        f.write(data)  # type: ignore[arg-type]

    return str(Path(output_path).resolve())
