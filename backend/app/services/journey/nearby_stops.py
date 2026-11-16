
import math

from geoalchemy2 import Geography
from sqlalchemy import cast, exists, func, select
from sqlalchemy.orm import Session

from app.models import Route, RouteStop, Stop


def find_nearby_stops(
    db: Session,
    longitude: float,
    latitude: float,
    radius_m: float = 1000,
    limit: int = 20,
) -> list[dict]:
    """
    Find active dala-dala stops within a radius of a coordinate.

    Distance is calculated in metres using PostGIS geography.
    Only stops connected to active routes are returned.

    Coordinates use (longitude, latitude).
    """

    # Validate coordinates.
    if not (
        math.isfinite(longitude)
        and math.isfinite(latitude)
    ):
        raise ValueError("Coordinates must be finite numbers.")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")

    if not math.isfinite(radius_m) or not 1 <= radius_m <= 5000:
        raise ValueError("Search radius must be between 1 and 5000 metres.")

    if not 1 <= limit <= 50:
        raise ValueError("Limit must be between 1 and 50.")

    # Create the search point using longitude, latitude order.
    search_point = func.ST_SetSRID(
        func.ST_MakePoint(longitude, latitude),
        4326,
    )

    # Cast both geometries to geography for metre-based calculations.
    stop_geography = cast(
        Stop.location,
        Geography(srid=4326),
    )

    search_geography = cast(
        search_point,
        Geography(srid=4326),
    )

    distance_expression = func.ST_Distance(
        stop_geography,
        search_geography,
    )

    # A stop must belong to at least one active dala-dala route.
    has_active_route = exists(
        select(1)
        .select_from(RouteStop)
        .join(Route, Route.id == RouteStop.route_id)
        .where(
            RouteStop.stop_id == Stop.id,
            Route.is_active.is_(True),
        )
    )

    query = (
        select(
            Stop.id,
            Stop.name,
            Stop.description,
            Stop.stop_type,
            Stop.is_verified,
            func.ST_X(Stop.location).label("longitude"),
            func.ST_Y(Stop.location).label("latitude"),
            distance_expression.label("distance_m"),
        )
        .where(
            Stop.is_active.is_(True),
            has_active_route,
            func.ST_DWithin(
                stop_geography,
                search_geography,
                radius_m,
            ),
        )
        .order_by(distance_expression.asc())
        .limit(limit)
    )

    rows = db.execute(query).mappings().all()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "stop_type": row["stop_type"],
            "is_verified": row["is_verified"],
            "longitude": float(row["longitude"]),
            "latitude": float(row["latitude"]),
            "distance_m": round(float(row["distance_m"]), 2),
        }
        for row in rows
    ]
