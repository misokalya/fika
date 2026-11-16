
import networkx as nx
import pytest

from app.services.transit.pathfinder import (
    TransitPathNotFoundError,
    find_transit_path,
)


@pytest.fixture
def sample_graph():
    graph = nx.MultiDiGraph()

    graph.add_edge(
        1, 2,
        kind="ride",
        weight=1,
        route_id=10,
    )

    graph.add_edge(
        2, 3,
        kind="transfer",
        weight=1,
        transfer_id=20,
        walking_distance_m=150,
    )

    graph.add_edge(
        3, 4,
        kind="ride",
        weight=1,
        route_id=11,
    )

    return graph


def test_finds_valid_transit_path(sample_graph):
    result = find_transit_path(sample_graph, 1, 4)

    assert result["origin_stop_id"] == 1
    assert result["destination_stop_id"] == 4
    assert result["stops"] == [1, 2, 3, 4]
    assert result["total_connections"] == 3


def test_correctly_counts_ride_and_transfer_connections(sample_graph):
    result = find_transit_path(sample_graph, 1, 4)

    assert result["ride_connections"] == 2
    assert result["transfer_connections"] == 1


def test_selects_lowest_weight_parallel_edge():
    graph = nx.MultiDiGraph()

    graph.add_edge(
        1, 2,
        kind="ride",
        weight=5,
        route_id=10,
    )

    graph.add_edge(
        1, 2,
        kind="transfer",
        weight=2,
        transfer_id=20,
    )

    result = find_transit_path(graph, 1, 2)

    assert result["total_connections"] == 1
    assert result["connections"][0]["kind"] == "transfer"
    assert result["connections"][0]["weight"] == 2
    assert result["connections"][0]["transfer_id"] == 20


def test_raises_error_when_no_path_exists():
    graph = nx.MultiDiGraph()

    graph.add_edge(1, 2, kind="ride", weight=1)
    graph.add_node(3)

    with pytest.raises(TransitPathNotFoundError):
        find_transit_path(graph, 1, 3)


def test_raises_error_when_origin_stop_is_missing():
    graph = nx.MultiDiGraph()
    graph.add_node(2)

    with pytest.raises(
        ValueError,
        match="Origin stop 1 does not exist",
    ):
        find_transit_path(graph, 1, 2)


def test_raises_error_when_destination_stop_is_missing():
    graph = nx.MultiDiGraph()
    graph.add_node(1)

    with pytest.raises(
        ValueError,
        match="Destination stop 2 does not exist",
    ):
        find_transit_path(graph, 1, 2)
