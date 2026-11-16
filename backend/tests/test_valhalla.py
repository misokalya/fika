
import httpx
import pytest

from app.services.routing.valhalla import (
    ValhallaProvider,
    ValhallaRoutingError,
)


@pytest.fixture
def valid_response():
    return {
        "trip": {
            "legs": [
                {
                    "summary": {
                        "length": 1.25,
                        "time": 420,
                        "cost": 500,
                    },
                    "shape": "encoded_polyline",
                    "maneuvers": [
                        {"instruction": "Continue straight"}
                    ],
                }
            ]
        }
    }


class FakeResponse:
    def __init__(self, data=None, status_error=None, json_error=None):
        self.data = data
        self.status_error = status_error
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.data


class FakeAsyncClient:
    def __init__(
        self,
        response=None,
        request_error=None,
        timeout_error=None,
        tracker=None,
        **kwargs,
    ):
        self.response = response
        self.request_error = request_error
        self.timeout_error = timeout_error
        self.tracker = tracker
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, json):
        if self.tracker is not None:
            self.tracker["url"] = url
            self.tracker["payload"] = json
            self.tracker["timeout"] = self.timeout

        if self.timeout_error:
            raise self.timeout_error

        if self.request_error:
            raise self.request_error

        return self.response


@pytest.mark.anyio
async def test_successful_route_response(monkeypatch, valid_response):
    def fake_client(**kwargs):
        return FakeAsyncClient(
            response=FakeResponse(data=valid_response)
        )

    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        fake_client,
    )

    provider = ValhallaProvider()

    result = await provider.get_route(
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
        costing="pedestrian",
    )

    assert result["provider"] == "valhalla"
    assert result["costing"] == "pedestrian"
    assert result["distance_km"] == 1.25
    assert result["duration_seconds"] == 420
    assert result["duration_minutes"] == 7
    assert result["cost"] == 500
    assert result["geometry"] == "encoded_polyline"
    assert result["maneuvers"][0]["instruction"] == "Continue straight"


@pytest.mark.anyio
async def test_request_uses_correct_coordinate_order(
    monkeypatch,
    valid_response,
):
    tracker = {}

    def fake_client(**kwargs):
        return FakeAsyncClient(
            response=FakeResponse(data=valid_response),
            tracker=tracker,
            **kwargs,
        )

    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        fake_client,
    )

    provider = ValhallaProvider(
        base_url="https://example.com/",
        timeout=10,
    )

    await provider.get_route(
        origin=(36.8219, -3.3869),
        destination=(36.825, -3.390),
        costing="pedestrian",
    )

    assert tracker["url"] == "https://example.com/route"
    assert tracker["timeout"] == 10

    assert tracker["payload"]["locations"] == [
        {"lat": -3.3869, "lon": 36.8219},
        {"lat": -3.390, "lon": 36.825},
    ]

    assert tracker["payload"]["costing"] == "pedestrian"
    assert tracker["payload"]["units"] == "kilometers"


@pytest.mark.parametrize(
    "coordinates",
    [
        (181, 0),
        (-181, 0),
        (0, 91),
        (0, -91),
        (float("nan"), 0),
        (0, float("inf")),
        (36.8,),
    ],
)
def test_invalid_origin_coordinates_are_rejected(coordinates):
    provider = ValhallaProvider()

    with pytest.raises(ValueError):
        provider._validate_coordinates(coordinates, "Origin")


@pytest.mark.anyio
async def test_invalid_destination_coordinates_are_rejected():
    provider = ValhallaProvider()

    with pytest.raises(ValueError, match="Destination"):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(200, 0),
            costing="pedestrian",
        )


@pytest.mark.anyio
async def test_missing_costing_profile_is_rejected():
    provider = ValhallaProvider()

    with pytest.raises(
        ValueError,
        match="costing profile is required",
    ):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(36.825, -3.390),
            costing="",
        )


@pytest.mark.anyio
async def test_http_error_is_converted_to_routing_error(monkeypatch):
    response = FakeResponse(
        status_error=httpx.HTTPStatusError(
            "Server error",
            request=httpx.Request("POST", "https://example.com/route"),
            response=httpx.Response(503),
        )
    )

    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(response=response),
    )

    provider = ValhallaProvider()

    with pytest.raises(ValhallaRoutingError, match="HTTP 503"):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(36.825, -3.390),
            costing="pedestrian",
        )


@pytest.mark.anyio
async def test_timeout_is_converted_to_routing_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            timeout_error=httpx.TimeoutException("Timed out")
        ),
    )

    provider = ValhallaProvider()

    with pytest.raises(ValhallaRoutingError, match="timed out"):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(36.825, -3.390),
            costing="pedestrian",
        )


@pytest.mark.anyio
async def test_connection_error_is_converted_to_routing_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(
            request_error=httpx.ConnectError("Connection refused")
        ),
    )

    provider = ValhallaProvider()

    with pytest.raises(
        ValhallaRoutingError,
        match="Could not connect",
    ):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(36.825, -3.390),
            costing="pedestrian",
        )


@pytest.mark.anyio
async def test_invalid_json_is_converted_to_routing_error(monkeypatch):
    response = FakeResponse(
        json_error=ValueError("Invalid JSON")
    )

    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(response=response),
    )

    provider = ValhallaProvider()

    with pytest.raises(
        ValhallaRoutingError,
        match="invalid JSON",
    ):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(36.825, -3.390),
            costing="pedestrian",
        )


@pytest.mark.anyio
async def test_unexpected_response_structure_is_rejected(monkeypatch):
    response = FakeResponse(data={"unexpected": "structure"})

    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(response=response),
    )

    provider = ValhallaProvider()

    with pytest.raises(
        ValhallaRoutingError,
        match="unexpected route structure",
    ):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(36.825, -3.390),
            costing="pedestrian",
        )


@pytest.mark.anyio
async def test_negative_route_measurements_are_rejected(monkeypatch):
    response = FakeResponse(
        data={
            "trip": {
                "legs": [
                    {
                        "summary": {
                            "length": -1,
                            "time": 100,
                        }
                    }
                ]
            }
        }
    )

    monkeypatch.setattr(
        "app.services.routing.valhalla.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(response=response),
    )

    provider = ValhallaProvider()

    with pytest.raises(
        ValhallaRoutingError,
        match="unexpected route structure",
    ):
        await provider.get_route(
            origin=(36.8219, -3.3869),
            destination=(36.825, -3.390),
            costing="pedestrian",
        )
