
import pytest

from app.services.journey import access
from app.services.routing.valhalla import ValhallaRoutingError


@pytest.fixture
def nearby_candidates():
    return [
        {
            "id": 1,
            "name": "Stop A",
            "longitude": 36.695,
            "latitude": -3.372,
            "distance_m": 100,
        },
        {
            "id": 2,
            "name": "Stop B",
            "longitude": 36.696,
            "latitude": -3.373,
            "distance_m": 200,
        },
        {
            "id": 3,
            "name": "Stop C",
            "longitude": 36.697,
            "latitude": -3.374,
            "distance_m": 300,
        },
    ]


class FakeValhallaProvider:
    def __init__(self, responses=None, errors=None, tracker=None):
        self.responses = responses or {}
        self.errors = errors or {}
        self.tracker = tracker if tracker is not None else []
    
    async def get_route(self, origin, destination, costing):
        self.tracker.append({
            "origin": origin,
            "destination": destination,
            "costing": costing,
        })

        stop_id = len(self.tracker)

        if stop_id in self.errors:
            raise self.errors[stop_id]

        return self.responses[stop_id]


@pytest.fixture
def fake_walking_routes():
    return {
        1: {
            "distance_km": 0.8,
            "duration_seconds": 480,
            "duration_minutes": 8,
            "geometry": "geometry_a",
        },
        2: {
            "distance_km": 0.5,
            "duration_seconds": 300,
            "duration_minutes": 5,
            "geometry": "geometry_b",
        },
        3: {
            "distance_km": 1.2,
            "duration_seconds": 720,
            "duration_minutes": 12,
            "geometry": "geometry_c",
        },
    }


@pytest.fixture
def patch_nearby_stops(monkeypatch, nearby_candidates):
    monkeypatch.setattr(
        access,
        "find_nearby_stops",
        lambda **kwargs: nearby_candidates,
    )


@pytest.mark.anyio
async def test_successful_routes_are_enriched_and_ranked(
    monkeypatch,
    nearby_candidates,
    fake_walking_routes,
):
    tracker = []

    monkeypatch.setattr(
        access,
        "find_nearby_stops",
        lambda **kwargs: nearby_candidates,
    )

    monkeypatch.setattr(
        access,
        "ValhallaProvider",
        lambda: FakeValhallaProvider(
            responses=fake_walking_routes,
            tracker=tracker,
        ),
    )

    results = await access.find_walking_access_routes(
        db=None,
        longitude=36.69438,
        latitude=-3.37238,
    )

    assert len(results) == 3

    # Ranked by actual walking duration.
    assert [item["id"] for item in results] == [2, 1, 3]

    assert results[0]["routing_status"] == "success"
    assert results[0]["walking_distance_km"] == 0.5
    assert results[0]["walking_duration_seconds"] == 300
    assert results[0]["walking_duration_minutes"] == 5
    assert results[0]["walking_geometry"] == "geometry_b"

    # Original stop information is preserved.
    assert results[0]["name"] == "Stop B"
    assert results[0]["distance_m"] == 200


@pytest.mark.anyio
async def test_uses_pedestrian_costing_and_correct_coordinates(
    monkeypatch,
    nearby_candidates,
    fake_walking_routes,
):
    tracker = []

    monkeypatch.setattr(
        access,
        "find_nearby_stops",
        lambda **kwargs: nearby_candidates,
    )

    monkeypatch.setattr(
        access,
        "ValhallaProvider",
        lambda: FakeValhallaProvider(
            responses=fake_walking_routes,
            tracker=tracker,
        ),
    )

    await access.find_walking_access_routes(
        db=None,
        longitude=36.69438,
        latitude=-3.37238,
    )

    assert len(tracker) == 3

    assert tracker[0] == {
        "origin": (36.69438, -3.37238),
        "destination": (36.695, -3.372),
        "costing": "pedestrian",
    }


@pytest.mark.anyio
async def test_failed_routes_are_retained_and_ranked_last(
    monkeypatch,
    nearby_candidates,
    fake_walking_routes,
):
    tracker = []

    monkeypatch.setattr(
        access,
        "find_nearby_stops",
        lambda **kwargs: nearby_candidates,
    )

    monkeypatch.setattr(
        access,
        "ValhallaProvider",
        lambda: FakeValhallaProvider(
            responses=fake_walking_routes,
            errors={
                2: ValhallaRoutingError("Routing service unavailable"),
            },
            tracker=tracker,
        ),
    )

    results = await access.find_walking_access_routes(
        db=None,
        longitude=36.69438,
        latitude=-3.37238,
    )

    assert len(results) == 3

    successful = [
        item for item in results
        if item["routing_status"] == "success"
    ]

    unavailable = [
        item for item in results
        if item["routing_status"] == "unavailable"
    ]

    assert len(successful) == 2
    assert len(unavailable) == 1

    assert unavailable[0]["id"] == 2
    assert unavailable[0]["routing_error"] == (
        "Routing service unavailable"
    )

    assert results[-1]["routing_status"] == "unavailable"


@pytest.mark.anyio
async def test_all_failed_routes_are_retained(
    monkeypatch,
    nearby_candidates,
):
    tracker = []

    monkeypatch.setattr(
        access,
        "find_nearby_stops",
        lambda **kwargs: nearby_candidates,
    )

    monkeypatch.setattr(
        access,
        "ValhallaProvider",
        lambda: FakeValhallaProvider(
            errors={
                1: ValhallaRoutingError("Failure A"),
                2: ValhallaRoutingError("Failure B"),
                3: ValhallaRoutingError("Failure C"),
            },
            tracker=tracker,
        ),
    )

    results = await access.find_walking_access_routes(
        db=None,
        longitude=36.69438,
        latitude=-3.37238,
    )

    assert len(results) == 3
    assert all(
        item["routing_status"] == "unavailable"
        for item in results
    )


@pytest.mark.anyio
async def test_returns_empty_list_without_calling_valhalla(
    monkeypatch,
):
    monkeypatch.setattr(
        access,
        "find_nearby_stops",
        lambda **kwargs: [],
    )

    def unexpected_provider():
        raise AssertionError(
            "Valhalla should not be initialized without candidates."
        )

    monkeypatch.setattr(
        access,
        "ValhallaProvider",
        unexpected_provider,
    )

    results = await access.find_walking_access_routes(
        db=None,
        longitude=36.69438,
        latitude=-3.37238,
    )

    assert results == []
