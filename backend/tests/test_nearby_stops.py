
import uuid

import pytest
from geoalchemy2.elements import WKTElement

from app.database import SessionLocal
from app.models import Route, RouteStop, Stop
from app.services.journey.nearby_stops import find_nearby_stops


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def create_stop(db, name, longitude, latitude, is_active=True):
    stop = Stop(
        name=name,
        description=f"Test stop: {name}",
        stop_type="dala_dala",
        location=WKTElement(
            f"POINT({longitude} {latitude})",
            srid=4326,
        ),
        is_verified=True,
        is_active=is_active,
    )
    db.add(stop)
    db.flush()
    return stop


def create_route_with_stops(db, stops, is_active=True):
    route = Route(
        code=f"TEST-{uuid.uuid4().hex[:8]}",
        name="Nearby Stops Test Route",
        is_active=is_active,
    )
    db.add(route)
    db.flush()

    for sequence, stop in enumerate(stops, start=1):
        db.add(
            RouteStop(
                route_id=route.id,
                stop_id=stop.id,
                sequence=sequence,
            )
        )

    db.flush()
    return route


def test_returns_nearby_stops_in_distance_order(db):
    origin_lon = 36.69438
    origin_lat = -3.37238

    nearest = create_stop(
        db, "Nearest Stop",
        origin_lon + 0.001, origin_lat,
    )
    farther = create_stop(
        db, "Farther Stop",
        origin_lon + 0.003, origin_lat,
    )

    create_route_with_stops(db, [nearest, farther])

    results = find_nearby_stops(
        db,
        longitude=origin_lon,
        latitude=origin_lat,
        radius_m=1000,
    )

    assert len(results) == 2
    assert results[0]["id"] == nearest.id
    assert results[1]["id"] == farther.id
    assert results[0]["distance_m"] < results[1]["distance_m"]


def test_excludes_stops_outside_search_radius(db):
    origin_lon = 36.69438
    origin_lat = -3.37238

    nearby = create_stop(
        db, "Nearby Stop",
        origin_lon + 0.001, origin_lat,
    )
    distant = create_stop(
        db, "Distant Stop",
        origin_lon + 0.02, origin_lat,
    )

    create_route_with_stops(db, [nearby, distant])

    results = find_nearby_stops(
        db,
        longitude=origin_lon,
        latitude=origin_lat,
        radius_m=500,
    )

    returned_ids = [item["id"] for item in results]

    assert nearby.id in returned_ids
    assert distant.id not in returned_ids


def test_excludes_inactive_stops(db):
    origin_lon = 36.69438
    origin_lat = -3.37238

    active = create_stop(
        db, "Active Stop",
        origin_lon + 0.001, origin_lat,
    )
    inactive = create_stop(
        db, "Inactive Stop",
        origin_lon + 0.002, origin_lat,
        is_active=False,
    )

    create_route_with_stops(db, [active, inactive])

    results = find_nearby_stops(
        db,
        longitude=origin_lon,
        latitude=origin_lat,
    )

    returned_ids = [item["id"] for item in results]

    assert active.id in returned_ids
    assert inactive.id not in returned_ids


def test_excludes_stops_without_active_routes(db):
    origin_lon = 36.69438
    origin_lat = -3.37238

    stop = create_stop(
        db, "Stop Without Active Route",
        origin_lon + 0.001, origin_lat,
    )

    create_route_with_stops(
        db,
        [stop],
        is_active=False,
    )

    results = find_nearby_stops(
        db,
        longitude=origin_lon,
        latitude=origin_lat,
    )

    assert stop.id not in [item["id"] for item in results]


def test_respects_result_limit(db):
    origin_lon = 36.69438
    origin_lat = -3.37238

    stops = [
        create_stop(
            db,
            f"Limit Stop {index}",
            origin_lon + (index * 0.0001),
            origin_lat,
        )
        for index in range(1, 5)
    ]

    create_route_with_stops(db, stops)

    results = find_nearby_stops(
        db,
        longitude=origin_lon,
        latitude=origin_lat,
        radius_m=1000,
        limit=2,
    )

    assert len(results) == 2


@pytest.mark.parametrize(
    "longitude, latitude",
    [
        (181, 0),
        (-181, 0),
        (0, 91),
        (0, -91),
        (float("nan"), 0),
        (0, float("inf")),
    ],
)
def test_rejects_invalid_coordinates(db, longitude, latitude):
    with pytest.raises(ValueError):
        find_nearby_stops(
            db,
            longitude=longitude,
            latitude=latitude,
        )


@pytest.mark.parametrize(
    "radius",
    [
        0,
        -1,
        5001,
        float("nan"),
        float("inf"),
    ],
)
def test_rejects_invalid_radius(db, radius):
    with pytest.raises(ValueError, match="Search radius"):
        find_nearby_stops(
            db,
            longitude=36.69438,
            latitude=-3.37238,
            radius_m=radius,
        )


@pytest.mark.parametrize("limit", [0, -1, 51])
def test_rejects_invalid_limit(db, limit):
    with pytest.raises(ValueError, match="Limit"):
        find_nearby_stops(
            db,
            longitude=36.69438,
            latitude=-3.37238,
            limit=limit,
        )


def test_returns_expected_coordinate_and_distance_fields(db):
    origin_lon = 36.69438
    origin_lat = -3.37238

    stop = create_stop(
        db,
        "Coordinate Test Stop",
        origin_lon + 0.001,
        origin_lat,
    )

    create_route_with_stops(db, [stop])

    results = find_nearby_stops(
        db,
        longitude=origin_lon,
        latitude=origin_lat,
    )

    result = next(
        item for item in results if item["id"] == stop.id
    )

    assert result["longitude"] == pytest.approx(
        origin_lon + 0.001,
    )
    assert result["latitude"] == pytest.approx(origin_lat)
    assert isinstance(result["distance_m"], float)
    assert result["distance_m"] > 0
    assert result["is_verified"] is True
