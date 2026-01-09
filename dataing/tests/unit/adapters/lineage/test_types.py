"""Tests for lineage types."""

import pytest

from dataing.adapters.lineage.types import (
    Dataset,
    DatasetId,
    DatasetType,
    LineageEdge,
    LineageGraph,
)


def test_lineage_graph_get_upstream():
    """Test getting upstream datasets from graph."""
    root = DatasetId(platform="snowflake", name="target")
    source1 = DatasetId(platform="snowflake", name="source1")
    source2 = DatasetId(platform="snowflake", name="source2")

    graph = LineageGraph(
        root=root,
        datasets={
            str(root): Dataset(
                id=root,
                name="target",
                qualified_name="target",
                dataset_type=DatasetType.TABLE,
                platform="snowflake",
            ),
            str(source1): Dataset(
                id=source1,
                name="source1",
                qualified_name="source1",
                dataset_type=DatasetType.TABLE,
                platform="snowflake",
            ),
            str(source2): Dataset(
                id=source2,
                name="source2",
                qualified_name="source2",
                dataset_type=DatasetType.TABLE,
                platform="snowflake",
            ),
        },
        edges=[
            LineageEdge(source=source1, target=root),
            LineageEdge(source=source2, target=root),
        ],
    )

    upstream = graph.get_upstream(root, depth=1)
    assert len(upstream) == 2
    assert {ds.name for ds in upstream} == {"source1", "source2"}


def test_lineage_graph_get_downstream():
    """Test getting downstream datasets from graph."""
    root = DatasetId(platform="snowflake", name="source")
    target1 = DatasetId(platform="snowflake", name="target1")
    target2 = DatasetId(platform="snowflake", name="target2")

    graph = LineageGraph(
        root=root,
        datasets={
            str(root): Dataset(
                id=root,
                name="source",
                qualified_name="source",
                dataset_type=DatasetType.TABLE,
                platform="snowflake",
            ),
            str(target1): Dataset(
                id=target1,
                name="target1",
                qualified_name="target1",
                dataset_type=DatasetType.TABLE,
                platform="snowflake",
            ),
            str(target2): Dataset(
                id=target2,
                name="target2",
                qualified_name="target2",
                dataset_type=DatasetType.TABLE,
                platform="snowflake",
            ),
        },
        edges=[
            LineageEdge(source=root, target=target1),
            LineageEdge(source=root, target=target2),
        ],
    )

    downstream = graph.get_downstream(root, depth=1)
    assert len(downstream) == 2
    assert {ds.name for ds in downstream} == {"target1", "target2"}


def test_lineage_graph_get_path():
    """Test finding path between datasets."""
    a = DatasetId(platform="snowflake", name="a")
    b = DatasetId(platform="snowflake", name="b")
    c = DatasetId(platform="snowflake", name="c")

    graph = LineageGraph(
        root=a,
        datasets={},
        edges=[
            LineageEdge(source=a, target=b),
            LineageEdge(source=b, target=c),
        ],
    )

    path = graph.get_path(a, c)
    assert path is not None
    assert len(path) == 2
    assert str(path[0].source) == str(a)
    assert str(path[0].target) == str(b)
    assert str(path[1].source) == str(b)
    assert str(path[1].target) == str(c)


def test_lineage_graph_get_path_not_found():
    """Test that get_path returns None when no path exists."""
    a = DatasetId(platform="snowflake", name="a")
    b = DatasetId(platform="snowflake", name="b")
    c = DatasetId(platform="snowflake", name="c")

    graph = LineageGraph(
        root=a,
        datasets={},
        edges=[
            LineageEdge(source=a, target=b),
            # c is not connected
        ],
    )

    path = graph.get_path(a, c)
    assert path is None


def test_lineage_graph_to_dict():
    """Test serializing graph to dict."""
    root = DatasetId(platform="snowflake", name="root")

    graph = LineageGraph(
        root=root,
        datasets={
            str(root): Dataset(
                id=root,
                name="root",
                qualified_name="db.schema.root",
                dataset_type=DatasetType.TABLE,
                platform="snowflake",
            ),
        },
        edges=[],
    )

    data = graph.to_dict()
    assert data["root"] == "snowflake://root"
    assert str(root) in data["datasets"]
    assert data["datasets"][str(root)]["name"] == "root"
