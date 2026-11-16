
from typing import Any

from sqlalchemy.orm import Session

from app.services.journey.nearby_stops import find_nearby_stops
from app.services.routing.mode_config import get_mode_config
from app.services.routing.valhalla import (
    ValhallaProvider,
    ValhallaRoutingError,
)


async def find_walking_access_routes(
    db: Session,
    longitude: float,
    latitude: float,
    radius_m: float = 2000,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Find nearby dala-dala stops and calculate walking routes
    from the passenger's origin to each candidate stop.

    Nearby-stop radius uses straight-line geographic distance.
    Access distance and duration use Valhalla pedestrian routing.
    """

    candidates = find_nearby_stops(
        db=db,
        longitude=longitude,
        latitude=latitude,
        radius_m=radius_m,
        limit=limit,
    )

    if not candidates:
        return []

    walking_config = get_mode_config("walking")
    provider = ValhallaProvider()

    results = []

    # Process sequentially to avoid sending unnecessary bursts
    # of requests to the public development routing service.
    for stop in candidates:
        try:
            walking_route = await provider.get_route(
                origin=(longitude, latitude),
                destination=(
                    stop["longitude"],
                    stop["latitude"],
                ),
                costing=walking_config["costing"],
            )

            results.append({
                **stop,
                "routing_status": "success",
                "walking_distance_km": walking_route["distance_km"],
                "walking_duration_seconds": (
                    walking_route["duration_seconds"]
                ),
                "walking_duration_minutes": (
                    walking_route["duration_minutes"]
                ),
                "walking_geometry": walking_route["geometry"],
            })

        except ValhallaRoutingError as exc:
            results.append({
                **stop,
                "routing_status": "unavailable",
                "routing_error": str(exc),
            })

    # Successful routes first, ordered by actual walking time.
    results.sort(
        key=lambda item: (
            item["routing_status"] != "success",
            item.get("walking_duration_seconds", float("inf")),
        )
    )

    return results
