
from typing import Any

from sqlalchemy.orm import Session

from app.services.journey.access import find_walking_access_routes
from app.services.journey.nearby_stops import find_nearby_stops
from app.services.journey.ranking import rank_journeys
from app.services.routing.mode_config import get_mode_config
from app.services.routing.valhalla import (
    ValhallaProvider,
    ValhallaRoutingError,
)
from app.services.transit.graph import build_transit_graph
from app.services.transit.pathfinder import (
    find_transit_path,
    TransitPathNotFoundError,
)
from app.services.transit.instructions import (
    generate_journey_instructions,
)


async def plan_coordinate_journey(
    db: Session,
    origin: tuple[float, float],
    destination: tuple[float, float],
    radius_m: float = 2000,
    candidate_limit: int = 10,
    include_unverified_transfers: bool = False,
) -> dict[str, Any]:
    """
    Plan a walking -> dala-dala -> walking journey.

    Coordinates use (longitude, latitude).

    Transit duration and fare are intentionally not estimated here.
    """

    origin_lon, origin_lat = origin
    destination_lon, destination_lat = destination

    # --------------------------------------------------
    # 1. Find and route walking access candidates.
    # --------------------------------------------------

    boarding_candidates = await find_walking_access_routes(
        db=db,
        longitude=origin_lon,
        latitude=origin_lat,
        radius_m=radius_m,
        limit=candidate_limit,
    )

    boarding_candidates = [
        stop
        for stop in boarding_candidates
        if stop["routing_status"] == "success"
    ]

    if not boarding_candidates:
        return {
            "status": "no_candidates",
            "message": "No reachable boarding stops were found near the origin.",
            "journeys": [],
        }

    # --------------------------------------------------
    # 2. Find potential alighting stops near destination.
    # --------------------------------------------------

    alighting_candidates = find_nearby_stops(
        db=db,
        longitude=destination_lon,
        latitude=destination_lat,
        radius_m=radius_m,
        limit=candidate_limit,
    )

    if not alighting_candidates:
        return {
            "status": "no_candidates",
            "message": "No active dala-dala stops were found near the destination.",
            "journeys": [],
        }

    # --------------------------------------------------
    # 3. Calculate walking egress routes.
    # --------------------------------------------------

    walking_config = get_mode_config("walking")
    provider = ValhallaProvider()

    routed_alighting_candidates = []

    for stop in alighting_candidates:
        try:
            egress_route = await provider.get_route(
                origin=(
                    stop["longitude"],
                    stop["latitude"],
                ),
                destination=(destination_lon, destination_lat),
                costing=walking_config["costing"],
            )

            routed_alighting_candidates.append({
                **stop,
                "routing_status": "success",
                "walking_distance_km": egress_route["distance_km"],
                "walking_duration_seconds": (
                    egress_route["duration_seconds"]
                ),
                "walking_duration_minutes": (
                    egress_route["duration_minutes"]
                ),
                "walking_geometry": egress_route["geometry"],
            })

        except ValhallaRoutingError:
            # Skip candidates without a usable walking route.
            continue

    if not routed_alighting_candidates:
        return {
            "status": "no_candidates",
            "message": "No usable walking routes were found from nearby alighting stops.",
            "journeys": [],
        }

    # --------------------------------------------------
    # 4. Build the dala-dala transit graph.
    # --------------------------------------------------

    graph = build_transit_graph(
        db,
        verified_transfers_only=not include_unverified_transfers,
    )

    # --------------------------------------------------
    # 5. Evaluate boarding/alighting combinations.
    # --------------------------------------------------

    journeys = []

    for boarding_stop in boarding_candidates:
        boarding_id = boarding_stop["id"]

        if boarding_id not in graph:
            continue

        for alighting_stop in routed_alighting_candidates:
            alighting_id = alighting_stop["id"]

            if alighting_id not in graph:
                continue

            if boarding_id == alighting_id:
                continue

            try:
                path_result = find_transit_path(
                    graph,
                    boarding_id,
                    alighting_id,
                )

            except TransitPathNotFoundError:
                continue

            # A valid FIKA transit journey must include
            # at least one actual dala-dala ride.
            if path_result["ride_connections"] < 1:
                continue

            instructions = generate_journey_instructions(
                graph,
                path_result,
            )

            access_seconds = boarding_stop[
                "walking_duration_seconds"
            ]

            egress_seconds = alighting_stop[
                "walking_duration_seconds"
            ]

            access_distance_m = (
                boarding_stop["walking_distance_km"] * 1000
            )

            egress_distance_m = (
                alighting_stop["walking_distance_km"] * 1000
            )

            journeys.append({
                "boarding_stop": {
                    "id": boarding_stop["id"],
                    "name": boarding_stop["name"],
                    "is_verified": boarding_stop["is_verified"],
                },
                "alighting_stop": {
                    "id": alighting_stop["id"],
                    "name": alighting_stop["name"],
                    "is_verified": alighting_stop["is_verified"],
                },
                "access": {
                    "mode": "walking",
                    "distance_m": round(access_distance_m, 2),
                    "duration_seconds": access_seconds,
                    "duration_minutes": round(
                        access_seconds / 60, 2
                    ),
                    "geometry": boarding_stop["walking_geometry"],
                },
                "transit": {
                    "mode": "dala_dala",
                    "path": path_result,
                    "instructions": instructions,
                    "duration_seconds": None,
                    "fare_tzs": None,
                },
                "egress": {
                    "mode": "walking",
                    "distance_m": round(egress_distance_m, 2),
                    "duration_seconds": egress_seconds,
                    "duration_minutes": round(
                        egress_seconds / 60, 2
                    ),
                    "geometry": alighting_stop["walking_geometry"],
                },
                "metrics": {
                    "total_walking_distance_m": round(
                        access_distance_m + egress_distance_m,
                        2,
                    ),
                    "total_walking_duration_seconds": (
                        access_seconds + egress_seconds
                    ),
                    "total_walking_duration_minutes": round(
                        (access_seconds + egress_seconds) / 60,
                        2,
                    ),
                    "transfer_count": path_result[
                        "transfer_connections"
                    ],
                },
            })

    # --------------------------------------------------
    # 6. Rank viable journeys.
    # --------------------------------------------------

    ranked_journeys = rank_journeys(journeys)

    if not ranked_journeys:
        return {
            "status": "no_journey_found",
            "message": (
                "Nearby boarding and alighting stops were found, "
                "but no connected dala-dala journey was available."
            ),
            "journeys": [],
        }

    return {
        "status": "success",
        "origin": {
            "longitude": origin_lon,
            "latitude": origin_lat,
        },
        "destination": {
            "longitude": destination_lon,
            "latitude": destination_lat,
        },
        "include_unverified_transfers": include_unverified_transfers,
        "ranking_method": (
            "Walking time, then transfer count, then walking distance."
        ),
        "estimation_notes": {
            "walking": "Calculated using Valhalla pedestrian routing.",
            "transit_duration": "Not yet estimated.",
            "fare": "Not yet estimated.",
        },
        "total_journeys": len(ranked_journeys),
        "journeys": ranked_journeys,
    }
