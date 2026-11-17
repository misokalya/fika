
import networkx as nx
import pytest

from app.services.journey import planner


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeValhallaProvider:
    """Returns a normal 500 m walking route."""

    async def get_route(self, origin, destination, costing):
        return {
            "distance_km": 0.5,
            "duration_seconds": 360,
            "duration_minutes": 6,
            "geometry": "fake_polyline",
        }


class ZeroForSameCoordinatesProvider:
    """Returns zero distance when coordinates are identical."""

    async def get_route(self, origin, destination, costing):
        if origin == destination:
            distance_km = 0
        else:
            distance_km = 0.5

        return {
            "distance_km": distance_km,
            "duration_seconds": 360,
            "duration_minutes": 6,
            "geometry": "fake_polyline",
        }

class TransferFailureProvider:
    """Allows egress routing but simulates a transfer-routing failure."""

    def __init__(self):
        self.call_count = 0

    async def get_route(self, origin, destination, costing):
        self.call_count += 1

        # First call: egress route succeeds.
        if self.call_count == 1:
            return {
                "distance_km": 0.5,
                "duration_seconds": 360,
                "duration_minutes": 6,
                "geometry": "egress_polyline",
            }

        # Second call: transfer route fails.
        raise planner.ValhallaRoutingError(
            "Simulated Valhalla routing failure"
        )

@pytest.fixture
def sample_stops():
    boarding = {
        "id": 1,
        "name": "Boarding Stop",
        "is_verified": True,
        "routing_status": "success",
        "walking_distance_km": 0.2,
        "walking_duration_seconds": 120,
        "walking_duration_minutes": 2,
        "walking_geometry": "access_polyline",
    }

    alighting = {
        "id": 2,
        "name": "Alighting Stop",
        "is_verified": True,
        "longitude": 36.825,
        "latitude": -3.390,
    }

    return boarding, alighting


@pytest.mark.anyio
async def test_direct_dala_dala_journey(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(
            1,
            longitude=36.8219,
            latitude=-3.3869,
        )

        graph.add_node(
            2,
            longitude=36.825,
            latitude=-3.390,
        )

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [origin_id, destination_id],
            "connections": [
                {
                    "kind": "ride",
                    "from_stop_id": origin_id,
                    "to_stop_id": destination_id,
                    "route_id": 1,
                }
            ],
            "total_connections": 1,
            "ride_connections": 1,
            "transfer_connections": 0,
        }

    def fake_instructions(graph, path_result):
        return {
            "steps": ["Board and ride to destination"],
            "total_steps": 1,
            "ride_steps": 1,
            "transfer_steps": 0,
        }

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )

    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )

    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )

    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )

    monkeypatch.setattr(
        planner,
        "generate_journey_instructions",
        fake_instructions,
    )

    # Normal provider: 500 m egress route.
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        FakeValhallaProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "success"
    assert result["total_journeys"] == 1

    journey = result["journeys"][0]

    assert journey["boarding_stop"]["id"] == 1
    assert journey["alighting_stop"]["id"] == 2

    assert journey["transit"]["mode"] == "dala_dala"
    assert journey["transit"]["duration_seconds"] is None
    assert journey["transit"]["fare_tzs"] is None

    assert journey["metrics"]["transfer_count"] == 0

    assert (
        journey["metrics"]["transfer_walking_distance_m"]
        == 0
    )

    assert (
        journey["metrics"]["total_walking_distance_m"]
        == 700
    )

    assert (
        journey["metrics"]["total_walking_duration_seconds"]
        == 480
    )

    assert journey["transfer_walks"] == []


@pytest.mark.anyio
async def test_no_reachable_boarding_candidates(monkeypatch):

    async def fake_access_routes(**kwargs):
        return [
            {
                "id": 1,
                "name": "Unreachable Stop",
                "routing_status": "unavailable",
            }
        ]

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "no_candidates"
    assert result["journeys"] == []

    assert (
        "No reachable boarding stops"
        in result["message"]
    )


@pytest.mark.anyio
async def test_transfer_with_identical_coordinates_uses_recorded_distance(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(
            1,
            longitude=36.8219,
            latitude=-3.3869,
        )

        graph.add_node(
            2,
            longitude=36.825,
            latitude=-3.390,
        )

        graph.add_node(
            3,
            longitude=36.825,
            latitude=-3.390,
        )

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [1, 2, 3],
            "connections": [
                {
                    "kind": "ride",
                    "from_stop_id": 1,
                    "to_stop_id": 2,
                },
                {
                    "kind": "transfer",
                    "from_stop_id": 2,
                    "to_stop_id": 3,
                    "transfer_id": 10,
                    "walking_distance_m": 150,
                },
            ],
            "total_connections": 2,
            "ride_connections": 1,
            "transfer_connections": 1,
        }

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )

    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )

    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )

    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )

    monkeypatch.setattr(
        planner,
        "generate_journey_instructions",
        lambda graph, path: {"steps": []},
    )

    # Special provider: identical coordinates return zero distance.
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        ZeroForSameCoordinatesProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
        include_unverified_transfers=True,
    )

    assert result["status"] == "success"

    journey = result["journeys"][0]
    transfer = journey["transfer_walks"][0]

    assert transfer["transfer_id"] == 10
    assert transfer["recorded_distance_m"] == 150
    assert transfer["routed_distance_m"] == 0
    assert transfer["effective_distance_m"] == 150

    assert transfer["routing_status"] == "coordinate_mismatch"
    assert transfer["duration_seconds"] is None

    assert (
        journey["metrics"]["transfer_walking_distance_m"]
        == 150
    )

    assert (
        journey["metrics"]["total_walking_duration_seconds"]
        is None
    )

@pytest.mark.anyio
async def test_transfer_routing_failure_preserves_recorded_distance(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(
            1,
            longitude=36.8219,
            latitude=-3.3869,
        )
        graph.add_node(
            2,
            longitude=36.825,
            latitude=-3.390,
        )
        graph.add_node(
            3,
            longitude=36.826,
            latitude=-3.391,
        )

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [1, 2, 3],
            "connections": [
                {
                    "kind": "ride",
                    "from_stop_id": 1,
                    "to_stop_id": 2,
                },
                {
                    "kind": "transfer",
                    "from_stop_id": 2,
                    "to_stop_id": 3,
                    "transfer_id": 11,
                    "walking_distance_m": 250,
                },
            ],
            "total_connections": 2,
            "ride_connections": 1,
            "transfer_connections": 1,
        }

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )
    monkeypatch.setattr(
        planner,
        "generate_journey_instructions",
        lambda graph, path: {"steps": []},
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        TransferFailureProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
        include_unverified_transfers=True,
    )

    assert result["status"] == "success"

    journey = result["journeys"][0]
    transfer = journey["transfer_walks"][0]

    assert transfer["transfer_id"] == 11
    assert transfer["recorded_distance_m"] == 250
    assert transfer["routed_distance_m"] is None
    assert transfer["effective_distance_m"] == 250

    assert transfer["routing_status"] == "unavailable"
    assert transfer["duration_seconds"] is None
    assert transfer["geometry"] is None

    assert (
        journey["metrics"]["transfer_walking_distance_m"]
        == 250
    )

    assert (
        journey["metrics"]["total_walking_duration_seconds"]
        is None
    )


@pytest.mark.anyio
async def test_successful_transfer_routing_uses_routed_distance(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(1, longitude=36.8219, latitude=-3.3869)
        graph.add_node(2, longitude=36.825, latitude=-3.390)
        graph.add_node(3, longitude=36.826, latitude=-3.391)

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [1, 2, 3],
            "connections": [
                {
                    "kind": "ride",
                    "from_stop_id": 1,
                    "to_stop_id": 2,
                },
                {
                    "kind": "transfer",
                    "from_stop_id": 2,
                    "to_stop_id": 3,
                    "transfer_id": 12,
                    "walking_distance_m": 250,
                },
            ],
            "total_connections": 2,
            "ride_connections": 1,
            "transfer_connections": 1,
        }

    monkeypatch.setattr(
        planner, "find_walking_access_routes", fake_access_routes
    )
    monkeypatch.setattr(
        planner, "find_nearby_stops", fake_nearby_stops
    )
    monkeypatch.setattr(
        planner, "build_transit_graph", fake_build_graph
    )
    monkeypatch.setattr(
        planner, "find_transit_path", fake_find_path
    )
    monkeypatch.setattr(
        planner,
        "generate_journey_instructions",
        lambda graph, path: {"steps": []},
    )
    monkeypatch.setattr(
        planner, "ValhallaProvider", FakeValhallaProvider
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
        include_unverified_transfers=True,
    )

    assert result["status"] == "success"

    journey = result["journeys"][0]
    transfer = journey["transfer_walks"][0]

    assert transfer["transfer_id"] == 12
    assert transfer["recorded_distance_m"] == 250
    assert transfer["routed_distance_m"] == 500
    assert transfer["effective_distance_m"] == 500
    assert transfer["routing_status"] == "success"
    assert transfer["duration_seconds"] == 360
    assert transfer["geometry"] == "fake_polyline"

    assert journey["metrics"]["transfer_walking_distance_m"] == 500
    assert journey["metrics"]["transfer_walking_duration_seconds"] == 360
    assert journey["metrics"]["total_walking_duration_seconds"] == 840


@pytest.mark.anyio
async def test_no_nearby_alighting_stops(monkeypatch, sample_stops):
    boarding, _ = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return []

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )

    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "no_candidates"
    assert result["journeys"] == []
    assert "No active dala-dala stops" in result["message"]


@pytest.mark.anyio
async def test_all_egress_routes_fail(monkeypatch, sample_stops):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    class FailingValhallaProvider:
        async def get_route(self, origin, destination, costing):
            raise planner.ValhallaRoutingError(
                "Simulated egress routing failure"
            )

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )

    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )

    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        FailingValhallaProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "no_candidates"
    assert result["journeys"] == []
    assert "No usable walking routes" in result["message"]


@pytest.mark.anyio
async def test_no_connected_transit_journey(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()
        graph.add_node(
            1,
            longitude=36.8219,
            latitude=-3.3869,
        )
        graph.add_node(
            2,
            longitude=36.825,
            latitude=-3.390,
        )
        return graph

    def fake_find_path(graph, origin_id, destination_id):
        raise planner.TransitPathNotFoundError(
            "No connected transit path."
        )

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        FakeValhallaProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "no_journey_found"
    assert result["journeys"] == []
    assert "no connected dala-dala journey" in result["message"]


@pytest.mark.anyio
async def test_boarding_stop_missing_from_graph(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        # Only the alighting stop exists in the graph.
        graph.add_node(
            2,
            longitude=36.825,
            latitude=-3.390,
        )

        return graph

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        FakeValhallaProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "no_journey_found"
    assert result["journeys"] == []


@pytest.mark.anyio
async def test_alighting_stop_missing_from_graph(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        # Only the boarding stop exists in the graph.
        graph.add_node(
            1,
            longitude=36.8219,
            latitude=-3.3869,
        )

        return graph

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        FakeValhallaProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "no_journey_found"
    assert result["journeys"] == []


@pytest.mark.anyio
async def test_path_without_dala_dala_ride_is_rejected(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(
            1,
            longitude=36.8219,
            latitude=-3.3869,
        )
        graph.add_node(
            2,
            longitude=36.825,
            latitude=-3.390,
        )

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [origin_id, destination_id],
            "connections": [
                {
                    "kind": "transfer",
                    "from_stop_id": origin_id,
                    "to_stop_id": destination_id,
                    "transfer_id": 20,
                    "walking_distance_m": 150,
                }
            ],
            "total_connections": 1,
            "ride_connections": 0,
            "transfer_connections": 1,
        }

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        FakeValhallaProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "no_journey_found"
    assert result["journeys"] == []


@pytest.mark.anyio
async def test_multiple_journeys_are_ranked_by_walking_duration(
    monkeypatch,
):
    boarding_slow = {
        "id": 1,
        "name": "Slower Boarding Stop",
        "is_verified": True,
        "routing_status": "success",
        "walking_distance_km": 0.3,
        "walking_duration_seconds": 300,
        "walking_duration_minutes": 5,
        "walking_geometry": "slow_access",
    }

    boarding_fast = {
        "id": 3,
        "name": "Faster Boarding Stop",
        "is_verified": True,
        "routing_status": "success",
        "walking_distance_km": 0.2,
        "walking_duration_seconds": 120,
        "walking_duration_minutes": 2,
        "walking_geometry": "fast_access",
    }

    alighting = {
        "id": 2,
        "name": "Destination Stop",
        "is_verified": True,
        "longitude": 36.825,
        "latitude": -3.390,
    }

    async def fake_access_routes(**kwargs):
        # Deliberately return the slower option first.
        return [boarding_slow, boarding_fast]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(
            1,
            longitude=36.8219,
            latitude=-3.3869,
        )
        graph.add_node(
            2,
            longitude=36.825,
            latitude=-3.390,
        )
        graph.add_node(
            3,
            longitude=36.823,
            latitude=-3.388,
        )

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [origin_id, destination_id],
            "connections": [
                {
                    "kind": "ride",
                    "from_stop_id": origin_id,
                    "to_stop_id": destination_id,
                    "route_id": origin_id,
                }
            ],
            "total_connections": 1,
            "ride_connections": 1,
            "transfer_connections": 0,
        }

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )
    monkeypatch.setattr(
        planner,
        "generate_journey_instructions",
        lambda graph, path: {"steps": []},
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        FakeValhallaProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
    )

    assert result["status"] == "success"
    assert result["total_journeys"] == 2

    # Faster option must rank first, despite being returned second.
    assert result["journeys"][0]["boarding_stop"]["id"] == 3
    assert result["journeys"][1]["boarding_stop"]["id"] == 1

    assert (
        result["journeys"][0]["metrics"]["total_walking_duration_seconds"]
        == 480
    )
    assert (
        result["journeys"][1]["metrics"]["total_walking_duration_seconds"]
        == 660
    )


@pytest.mark.anyio
async def test_multiple_transfers_with_one_routing_failure(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(1, longitude=36.8219, latitude=-3.3869)
        graph.add_node(2, longitude=36.823, latitude=-3.388)
        graph.add_node(3, longitude=36.824, latitude=-3.389)
        graph.add_node(4, longitude=36.825, latitude=-3.390)
        graph.add_node(5, longitude=36.826, latitude=-3.391)

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [1, 2, 3, 4, 5],
            "connections": [
                {
                    "kind": "ride",
                    "from_stop_id": 1,
                    "to_stop_id": 2,
                    "route_id": 1,
                },
                {
                    "kind": "transfer",
                    "from_stop_id": 2,
                    "to_stop_id": 3,
                    "transfer_id": 101,
                    "walking_distance_m": 150,
                },
                {
                    "kind": "ride",
                    "from_stop_id": 3,
                    "to_stop_id": 4,
                    "route_id": 2,
                },
                {
                    "kind": "transfer",
                    "from_stop_id": 4,
                    "to_stop_id": 5,
                    "transfer_id": 102,
                    "walking_distance_m": 250,
                },
            ],
            "total_connections": 4,
            "ride_connections": 2,
            "transfer_connections": 2,
        }

    class PartialTransferFailureProvider:
        def __init__(self):
            self.call_count = 0

        async def get_route(self, origin, destination, costing):
            self.call_count += 1

            # Call 1: egress succeeds.
            # Call 2: first transfer succeeds.
            if self.call_count <= 2:
                return {
                    "distance_km": 0.5,
                    "duration_seconds": 360,
                    "duration_minutes": 6,
                    "geometry": f"route_{self.call_count}",
                }

            # Call 3: second transfer fails.
            raise planner.ValhallaRoutingError(
                "Simulated failure on second transfer"
            )

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )
    monkeypatch.setattr(
        planner,
        "generate_journey_instructions",
        lambda graph, path: {"steps": []},
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        PartialTransferFailureProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
        include_unverified_transfers=True,
    )

    assert result["status"] == "success"
    assert result["total_journeys"] == 1

    journey = result["journeys"][0]
    transfers = journey["transfer_walks"]

    assert len(transfers) == 2

    first_transfer = transfers[0]
    second_transfer = transfers[1]

    # First transfer routed successfully.
    assert first_transfer["transfer_id"] == 101
    assert first_transfer["recorded_distance_m"] == 150
    assert first_transfer["routed_distance_m"] == 500
    assert first_transfer["effective_distance_m"] == 500
    assert first_transfer["routing_status"] == "success"
    assert first_transfer["duration_seconds"] == 360

    # Second transfer failed and retains its recorded estimate.
    assert second_transfer["transfer_id"] == 102
    assert second_transfer["recorded_distance_m"] == 250
    assert second_transfer["routed_distance_m"] is None
    assert second_transfer["effective_distance_m"] == 250
    assert second_transfer["routing_status"] == "unavailable"
    assert second_transfer["duration_seconds"] is None

    # Distance remains available using routed + recorded distances.
    assert journey["metrics"]["transfer_walking_distance_m"] == 750

    # Aggregate transfer duration is unknown because one transfer failed.
    assert (
        journey["metrics"]["transfer_walking_duration_seconds"]
        is None
    )

    # Total walking duration must also remain unknown.
    assert (
        journey["metrics"]["total_walking_duration_seconds"]
        is None
    )

    # Total duration must remain unknown because one transfer failed.
    assert (
        journey["metrics"]["total_walking_duration_seconds"]
        is None
    )


@pytest.mark.anyio
async def test_zero_distance_transfer_without_recorded_distance(
    monkeypatch,
    sample_stops,
):
    boarding, alighting = sample_stops

    async def fake_access_routes(**kwargs):
        return [boarding]

    def fake_nearby_stops(**kwargs):
        return [alighting]

    def fake_build_graph(db, verified_transfers_only=True):
        graph = nx.MultiDiGraph()

        graph.add_node(1, longitude=36.8219, latitude=-3.3869)
        graph.add_node(2, longitude=36.824, latitude=-3.389)
        graph.add_node(3, longitude=36.825, latitude=-3.390)

        return graph

    def fake_find_path(graph, origin_id, destination_id):
        return {
            "origin_stop_id": origin_id,
            "destination_stop_id": destination_id,
            "stops": [1, 2, 3],
            "connections": [
                {
                    "kind": "ride",
                    "from_stop_id": 1,
                    "to_stop_id": 2,
                },
                {
                    "kind": "transfer",
                    "from_stop_id": 2,
                    "to_stop_id": 3,
                    "transfer_id": 103,
                    "walking_distance_m": None,
                },
            ],
            "total_connections": 2,
            "ride_connections": 1,
            "transfer_connections": 1,
        }

    class ZeroDistanceProvider:
        def __init__(self):
            self.call_count = 0

        async def get_route(self, origin, destination, costing):
            self.call_count += 1

            # First call is the egress route.
            if self.call_count == 1:
                return {
                    "distance_km": 0.5,
                    "duration_seconds": 360,
                    "duration_minutes": 6,
                    "geometry": "egress_polyline",
                }

            # Second call is the transfer route.
            return {
                "distance_km": 0,
                "duration_seconds": 0,
                "duration_minutes": 0,
                "geometry": None,
            }

    monkeypatch.setattr(
        planner,
        "find_walking_access_routes",
        fake_access_routes,
    )
    monkeypatch.setattr(
        planner,
        "find_nearby_stops",
        fake_nearby_stops,
    )
    monkeypatch.setattr(
        planner,
        "build_transit_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        planner,
        "find_transit_path",
        fake_find_path,
    )
    monkeypatch.setattr(
        planner,
        "generate_journey_instructions",
        lambda graph, path: {"steps": []},
    )
    monkeypatch.setattr(
        planner,
        "ValhallaProvider",
        ZeroDistanceProvider,
    )

    result = await planner.plan_coordinate_journey(
        db=None,
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
        include_unverified_transfers=True,
    )

    assert result["status"] == "success"

    journey = result["journeys"][0]
    transfer = journey["transfer_walks"][0]

    assert transfer["transfer_id"] == 103
    assert transfer["recorded_distance_m"] == 0
    assert transfer["routed_distance_m"] == 0
    assert transfer["effective_distance_m"] == 0

    # Zero distance between distinct transfer stops is unresolved.
    assert transfer["routing_status"] == "coordinate_mismatch"
    assert transfer["duration_seconds"] is None

    # FIKA must not claim a complete walking-duration estimate.
    assert (
        journey["metrics"]["total_walking_duration_seconds"]
        is None
    )
