
import networkx as nx
import pytest

from app.services.journey import planner


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeValhallaProvider:
    async def get_route(self, origin, destination, costing):
        return {
            "distance_km": 0.5,
            "duration_seconds": 360,
            "duration_minutes": 6,
            "geometry": "fake_polyline",
        }


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
    assert journey["metrics"]["transfer_walking_distance_m"] == 0
    assert journey["metrics"]["total_walking_distance_m"] == 700
    assert journey["metrics"]["total_walking_duration_seconds"] == 480

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
    assert "No reachable boarding stops" in result["message"]
