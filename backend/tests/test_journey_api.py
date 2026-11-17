
import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db
from app.routers import journeys


class FakeStop:
    def __init__(self, stop_id, is_active=True):
        self.id = stop_id
        self.is_active = is_active


class FakeDB:
    def __init__(self, stops=None):
        self.stops = stops or {}

    def get(self, model, stop_id):
        return self.stops.get(stop_id)


@pytest.fixture
def fake_db():
    return FakeDB({
        1: FakeStop(1),
        2: FakeStop(2),
        3: FakeStop(3, is_active=False),
    })


@pytest.fixture
def client(fake_db):
    def override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def fake_graph():
    graph = nx.MultiDiGraph()
    graph.add_node(1)
    graph.add_node(2)
    return graph


@pytest.fixture
def fake_path_result():
    return {
        "origin_stop_id": 1,
        "destination_stop_id": 2,
        "stops": [1, 2],
        "connections": [],
        "total_connections": 1,
        "ride_connections": 1,
        "transfer_connections": 0,
    }


@pytest.fixture
def fake_instructions():
    return {
        "origin_stop_id": 1,
        "destination_stop_id": 2,
        "steps": [],
        "total_steps": 1,
        "ride_steps": 1,
        "transfer_steps": 0,
    }


def test_stop_based_journey_success(
    client,
    monkeypatch,
    fake_graph,
    fake_path_result,
    fake_instructions,
):
    monkeypatch.setattr(
        journeys,
        "build_transit_graph",
        lambda db, verified_transfers_only=True: fake_graph,
    )

    monkeypatch.setattr(
        journeys,
        "find_transit_path",
        lambda graph, origin, destination: fake_path_result,
    )

    monkeypatch.setattr(
        journeys,
        "generate_journey_instructions",
        lambda graph, path: fake_instructions,
    )

    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 1,
            "destination_stop_id": 2,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "success"
    assert data["origin_stop_id"] == 1
    assert data["destination_stop_id"] == 2
    assert data["include_unverified_transfers"] is False
    assert data["path"] == fake_path_result
    assert data["instructions"] == fake_instructions


def test_stop_based_journey_allows_unverified_transfers(
    client,
    monkeypatch,
    fake_graph,
    fake_path_result,
    fake_instructions,
):
    tracker = {}

    def fake_build_graph(db, verified_transfers_only=True):
        tracker["verified_only"] = verified_transfers_only
        return fake_graph

    monkeypatch.setattr(
        journeys,
        "build_transit_graph",
        fake_build_graph,
    )

    monkeypatch.setattr(
        journeys,
        "find_transit_path",
        lambda graph, origin, destination: fake_path_result,
    )

    monkeypatch.setattr(
        journeys,
        "generate_journey_instructions",
        lambda graph, path: fake_instructions,
    )

    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 1,
            "destination_stop_id": 2,
            "include_unverified_transfers": True,
        },
    )

    assert response.status_code == 200
    assert tracker["verified_only"] is False
    assert response.json()["include_unverified_transfers"] is True


def test_missing_origin_stop_returns_404(client):
    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 99,
            "destination_stop_id": 2,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Origin stop not found or inactive."
    )


def test_inactive_origin_stop_returns_404(client):
    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 3,
            "destination_stop_id": 2,
        },
    )

    assert response.status_code == 404


def test_missing_destination_stop_returns_404(client):
    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 1,
            "destination_stop_id": 99,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Destination stop not found or inactive."
    )


def test_origin_without_active_route_returns_422(
    client,
    monkeypatch,
):
    graph = nx.MultiDiGraph()
    graph.add_node(2)

    monkeypatch.setattr(
        journeys,
        "build_transit_graph",
        lambda db, verified_transfers_only=True: graph,
    )

    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 1,
            "destination_stop_id": 2,
        },
    )

    assert response.status_code == 422
    assert "Origin stop" in response.json()["detail"]


def test_destination_without_active_route_returns_422(
    client,
    monkeypatch,
):
    graph = nx.MultiDiGraph()
    graph.add_node(1)

    monkeypatch.setattr(
        journeys,
        "build_transit_graph",
        lambda db, verified_transfers_only=True: graph,
    )

    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 1,
            "destination_stop_id": 2,
        },
    )

    assert response.status_code == 422
    assert "Destination stop" in response.json()["detail"]


def test_no_transit_path_returns_404(
    client,
    monkeypatch,
    fake_graph,
):
    monkeypatch.setattr(
        journeys,
        "build_transit_graph",
        lambda db, verified_transfers_only=True: fake_graph,
    )

    def raise_no_path(graph, origin, destination):
        raise journeys.TransitPathNotFoundError(
            "No path found"
        )

    monkeypatch.setattr(
        journeys,
        "find_transit_path",
        raise_no_path,
    )

    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 1,
            "destination_stop_id": 2,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "No transit journey was found between these stops."
    )


def test_same_stop_ids_are_rejected(client):
    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 1,
            "destination_stop_id": 1,
        },
    )

    assert response.status_code == 422


def test_invalid_stop_id_is_rejected(client):
    response = client.post(
        "/api/v1/journeys/plan",
        json={
            "origin_stop_id": 0,
            "destination_stop_id": 2,
        },
    )

    assert response.status_code == 422


def test_coordinate_journey_success(client, monkeypatch):
    expected_result = {
        "status": "success",
        "total_journeys": 1,
        "journeys": [],
    }

    async def fake_planner(
        db,
        origin,
        destination,
        radius_m,
        candidate_limit,
        include_unverified_transfers,
    ):
        assert origin == (36.69438, -3.37238)
        assert destination == (36.70000, -3.37000)
        assert radius_m == 2000
        assert candidate_limit == 10
        assert include_unverified_transfers is False

        return expected_result

    monkeypatch.setattr(
        journeys,
        "plan_coordinate_journey",
        fake_planner,
    )

    response = client.post(
        "/api/v1/journeys/plan-coordinates",
        json={
            "origin_longitude": 36.69438,
            "origin_latitude": -3.37238,
            "destination_longitude": 36.70000,
            "destination_latitude": -3.37000,
        },
    )

    assert response.status_code == 200
    assert response.json() == expected_result


def test_coordinate_journey_passes_custom_parameters(
    client,
    monkeypatch,
):
    tracker = {}

    async def fake_planner(
        db,
        origin,
        destination,
        radius_m,
        candidate_limit,
        include_unverified_transfers,
    ):
        tracker["radius_m"] = radius_m
        tracker["candidate_limit"] = candidate_limit
        tracker["include_unverified_transfers"] = (
            include_unverified_transfers
        )

        return {"status": "success", "journeys": []}

    monkeypatch.setattr(
        journeys,
        "plan_coordinate_journey",
        fake_planner,
    )

    response = client.post(
        "/api/v1/journeys/plan-coordinates",
        json={
            "origin_longitude": 36.69438,
            "origin_latitude": -3.37238,
            "destination_longitude": 36.70000,
            "destination_latitude": -3.37000,
            "radius_m": 1500,
            "candidate_limit": 5,
            "include_unverified_transfers": True,
        },
    )

    assert response.status_code == 200
    assert tracker == {
        "radius_m": 1500,
        "candidate_limit": 5,
        "include_unverified_transfers": True,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {
            "origin_longitude": 181,
            "origin_latitude": 0,
            "destination_longitude": 36.7,
            "destination_latitude": -3.37,
        },
        {
            "origin_longitude": 36.7,
            "origin_latitude": 91,
            "destination_longitude": 36.7,
            "destination_latitude": -3.37,
        },
        {
            "origin_longitude": 36.7,
            "origin_latitude": -3.37,
            "destination_longitude": 36.7,
            "destination_latitude": -91,
        },
        {
            "origin_longitude": 36.7,
            "origin_latitude": -3.37,
            "destination_longitude": 36.7,
            "destination_latitude": -3.37,
            "radius_m": 0,
        },
        {
            "origin_longitude": 36.7,
            "origin_latitude": -3.37,
            "destination_longitude": 36.7,
            "destination_latitude": -3.37,
            "candidate_limit": 51,
        },
    ],
)
def test_invalid_coordinate_request_returns_422(client, payload):
    response = client.post(
        "/api/v1/journeys/plan-coordinates",
        json=payload,
    )

    assert response.status_code == 422
