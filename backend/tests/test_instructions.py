
import networkx as nx
import pytest

from app.services.transit.instructions import (
    generate_journey_instructions,
)


@pytest.fixture
def sample_graph():
    graph = nx.MultiDiGraph()

    stops = {
        1: "Clock Tower",
        2: "Soko Kuu",
        3: "Sanawari",
        4: "Njiro",
    }

    for stop_id, name in stops.items():
        graph.add_node(stop_id, name=name)

    return graph


def make_path_result(connections):
    return {
        "origin_stop_id": 1,
        "destination_stop_id": 4,
        "connections": connections,
    }


def test_consecutive_rides_on_same_route_are_grouped(sample_graph):
    connections = [
        {
            "kind": "ride",
            "from_stop_id": 1,
            "to_stop_id": 2,
            "route_id": 10,
            "route_code": "AR-01",
            "route_name": "Town - Njiro",
            "destination_board": "Njiro",
        },
        {
            "kind": "ride",
            "from_stop_id": 2,
            "to_stop_id": 3,
            "route_id": 10,
            "route_code": "AR-01",
            "route_name": "Town - Njiro",
            "destination_board": "Njiro",
        },
    ]

    result = generate_journey_instructions(
        sample_graph,
        make_path_result(connections),
    )

    assert result["total_steps"] == 1
    assert result["ride_steps"] == 1
    assert result["transfer_steps"] == 0

    ride = result["steps"][0]

    assert ride["type"] == "ride"
    assert ride["route_id"] == 10
    assert ride["boarding_stop"]["name"] == "Clock Tower"
    assert ride["alighting_stop"]["name"] == "Sanawari"
    assert ride["stop_ids"] == [1, 2, 3]
    assert "AR-01" in ride["instruction"]
    assert "Njiro" in ride["instruction"]


def test_different_routes_create_separate_ride_steps(sample_graph):
    connections = [
        {
            "kind": "ride",
            "from_stop_id": 1,
            "to_stop_id": 2,
            "route_id": 10,
            "route_code": "AR-01",
            "route_name": "Town - Soko Kuu",
            "destination_board": "Soko Kuu",
        },
        {
            "kind": "ride",
            "from_stop_id": 2,
            "to_stop_id": 4,
            "route_id": 20,
            "route_code": "AR-02",
            "route_name": "Soko Kuu - Njiro",
            "destination_board": "Njiro",
        },
    ]

    result = generate_journey_instructions(
        sample_graph,
        make_path_result(connections),
    )

    assert result["total_steps"] == 2
    assert result["ride_steps"] == 2
    assert result["transfer_steps"] == 0

    assert result["steps"][0]["route_id"] == 10
    assert result["steps"][1]["route_id"] == 20

    assert result["steps"][0]["step_number"] == 1
    assert result["steps"][1]["step_number"] == 2


def test_verified_transfer_generates_transfer_instruction(sample_graph):
    connections = [
        {
            "kind": "ride",
            "from_stop_id": 1,
            "to_stop_id": 2,
            "route_id": 10,
            "route_code": "AR-01",
            "route_name": "Town - Soko Kuu",
            "destination_board": "Soko Kuu",
        },
        {
            "kind": "transfer",
            "from_stop_id": 2,
            "to_stop_id": 3,
            "transfer_id": 50,
            "walking_distance_m": 150,
            "is_verified": True,
            "notes": "Use the pedestrian crossing.",
        },
    ]

    result = generate_journey_instructions(
        sample_graph,
        make_path_result(connections),
    )

    assert result["total_steps"] == 2
    assert result["ride_steps"] == 1
    assert result["transfer_steps"] == 1

    transfer = result["steps"][1]

    assert transfer["type"] == "transfer"
    assert transfer["transfer_id"] == 50
    assert transfer["walking_distance_m"] == 150
    assert transfer["is_verified"] is True
    assert transfer["from_stop"]["name"] == "Soko Kuu"
    assert transfer["to_stop"]["name"] == "Sanawari"
    assert "150 m" in transfer["instruction"]
    assert "unverified estimate" not in transfer["instruction"]


def test_unverified_transfer_is_labelled_as_estimate(sample_graph):
    connections = [
        {
            "kind": "transfer",
            "from_stop_id": 2,
            "to_stop_id": 3,
            "transfer_id": 51,
            "walking_distance_m": 200,
            "is_verified": False,
        }
    ]

    result = generate_journey_instructions(
        sample_graph,
        make_path_result(connections),
    )

    transfer = result["steps"][0]

    assert transfer["is_verified"] is False
    assert "unverified estimate" in transfer["instruction"]
    assert "200 m" in transfer["instruction"]


def test_transfer_without_distance_does_not_display_distance(sample_graph):
    connections = [
        {
            "kind": "transfer",
            "from_stop_id": 2,
            "to_stop_id": 3,
            "transfer_id": 52,
            "walking_distance_m": None,
            "is_verified": False,
        }
    ]

    result = generate_journey_instructions(
        sample_graph,
        make_path_result(connections),
    )

    transfer = result["steps"][0]

    assert transfer["walking_distance_m"] is None
    assert "unverified estimate" in transfer["instruction"]
    assert "Recorded walking distance" not in transfer["instruction"]


def test_mixed_journey_has_correct_step_order_and_numbering(sample_graph):
    connections = [
        {
            "kind": "ride",
            "from_stop_id": 1,
            "to_stop_id": 2,
            "route_id": 10,
            "route_code": "AR-01",
            "route_name": "Town - Soko Kuu",
            "destination_board": "Soko Kuu",
        },
        {
            "kind": "transfer",
            "from_stop_id": 2,
            "to_stop_id": 3,
            "transfer_id": 60,
            "walking_distance_m": 100,
            "is_verified": True,
        },
        {
            "kind": "ride",
            "from_stop_id": 3,
            "to_stop_id": 4,
            "route_id": 20,
            "route_code": "AR-02",
            "route_name": "Sanawari - Njiro",
            "destination_board": "Njiro",
        },
    ]

    result = generate_journey_instructions(
        sample_graph,
        make_path_result(connections),
    )

    assert result["total_steps"] == 3
    assert result["ride_steps"] == 2
    assert result["transfer_steps"] == 1

    assert [
        step["type"] for step in result["steps"]
    ] == ["ride", "transfer", "ride"]

    assert [
        step["step_number"] for step in result["steps"]
    ] == [1, 2, 3]

    assert result["origin_stop_id"] == 1
    assert result["destination_stop_id"] == 4
