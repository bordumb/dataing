"""Graph utilities for lineage traversal and merging."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dataing.adapters.lineage.types import (
    Dataset,
    DatasetId,
    LineageEdge,
    LineageGraph,
)

if TYPE_CHECKING:
    from dataing.adapters.lineage.base import BaseLineageAdapter


async def build_graph_from_traversal(
    adapter: BaseLineageAdapter,
    root: DatasetId,
    upstream_depth: int = 3,
    downstream_depth: int = 3,
) -> LineageGraph:
    """Build a LineageGraph by traversing upstream and downstream.

    This function builds a complete lineage graph by calling the adapter's
    get_upstream and get_downstream methods recursively.

    Args:
        adapter: The lineage adapter to use for traversal.
        root: The root dataset ID to start from.
        upstream_depth: How many levels to traverse upstream.
        downstream_depth: How many levels to traverse downstream.

    Returns:
        LineageGraph with all discovered datasets and edges.
    """
    graph = LineageGraph(root=root)
    datasets: dict[str, Dataset] = {}
    edges: list[LineageEdge] = []

    # Get root dataset if available
    root_dataset = await adapter.get_dataset(root)
    if root_dataset:
        datasets[str(root)] = root_dataset

    # Traverse upstream
    await _traverse_direction(
        adapter=adapter,
        current_id=root,
        depth=upstream_depth,
        datasets=datasets,
        edges=edges,
        direction="upstream",
    )

    # Traverse downstream
    await _traverse_direction(
        adapter=adapter,
        current_id=root,
        depth=downstream_depth,
        datasets=datasets,
        edges=edges,
        direction="downstream",
    )

    graph.datasets = datasets
    graph.edges = edges

    return graph


async def _traverse_direction(
    adapter: BaseLineageAdapter,
    current_id: DatasetId,
    depth: int,
    datasets: dict[str, Dataset],
    edges: list[LineageEdge],
    direction: str,
    visited: set[str] | None = None,
) -> None:
    """Traverse in one direction (upstream or downstream).

    Args:
        adapter: The lineage adapter.
        current_id: Current dataset ID.
        depth: Remaining depth to traverse.
        datasets: Accumulated datasets dict.
        edges: Accumulated edges list.
        direction: "upstream" or "downstream".
        visited: Set of visited dataset IDs.
    """
    if depth <= 0:
        return

    if visited is None:
        visited = set()

    if str(current_id) in visited:
        return

    visited.add(str(current_id))

    # Get related datasets
    if direction == "upstream":
        related = await adapter.get_upstream(current_id, depth=1)
    else:
        related = await adapter.get_downstream(current_id, depth=1)

    for dataset in related:
        # Add dataset if not already present
        if str(dataset.id) not in datasets:
            datasets[str(dataset.id)] = dataset

        # Add edge
        if direction == "upstream":
            edge = LineageEdge(source=dataset.id, target=current_id)
        else:
            edge = LineageEdge(source=current_id, target=dataset.id)

        # Avoid duplicate edges
        if not _edge_exists(edges, edge):
            edges.append(edge)

        # Recurse
        await _traverse_direction(
            adapter=adapter,
            current_id=dataset.id,
            depth=depth - 1,
            datasets=datasets,
            edges=edges,
            direction=direction,
            visited=visited,
        )


def _edge_exists(edges: list[LineageEdge], new_edge: LineageEdge) -> bool:
    """Check if an edge already exists in the list.

    Args:
        edges: Existing edges.
        new_edge: Edge to check.

    Returns:
        True if edge exists, False otherwise.
    """
    for edge in edges:
        if str(edge.source) == str(new_edge.source) and str(edge.target) == str(new_edge.target):
            return True
    return False


def merge_graphs(graphs: list[LineageGraph]) -> LineageGraph:
    """Merge multiple lineage graphs into one.

    Used by CompositeLineageAdapter to combine lineage from multiple sources.
    Later graphs' datasets take precedence in case of conflicts.

    Args:
        graphs: List of LineageGraph objects to merge.

    Returns:
        Merged LineageGraph.

    Raises:
        ValueError: If graphs list is empty.
    """
    if not graphs:
        raise ValueError("Cannot merge empty list of graphs")

    # Use first graph's root
    merged = LineageGraph(root=graphs[0].root)

    # Merge datasets (later graphs take precedence)
    all_datasets: dict[str, Dataset] = {}
    for graph in graphs:
        all_datasets.update(graph.datasets)
    merged.datasets = all_datasets

    # Merge edges (deduplicate)
    all_edges: list[LineageEdge] = []
    for graph in graphs:
        for edge in graph.edges:
            if not _edge_exists(all_edges, edge):
                all_edges.append(edge)
    merged.edges = all_edges

    # Merge jobs
    all_jobs = {}
    for graph in graphs:
        all_jobs.update(graph.jobs)
    merged.jobs = all_jobs

    return merged
