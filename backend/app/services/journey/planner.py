
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

    Access, egress and transfer walking routes use Valhalla.
    Recorded transfer distances are preserved as fallback values.

    Transit duration and fare are not yet estimated.
    """

    origin_lon, origin_lat = origin
    destination_lon, destination_lat = destination

    # --------------------------------------------------
    # 1. Find reachable boarding stops near the origin
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
            "message": (
                "No reachable boarding stops were found near the origin."
            ),
            "journeys": [],
        }

    # --------------------------------------------------
    # 2. Find possible alighting stops near destination
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
            "message": (
                "No active dala-dala stops were found near the destination."
            ),
            "journeys": [],
        }

    # --------------------------------------------------
    # 3. Calculate walking egress routes
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
                destination=(
                    destination_lon,
                    destination_lat,
                ),
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
            continue

    if not routed_alighting_candidates:
        return {
            "status": "no_candidates",
            "message": (
                "No usable walking routes were found "
                "from nearby alighting stops."
            ),
            "journeys": [],
        }

    # --------------------------------------------------
    # 4. Build the dala-dala transit graph
    # --------------------------------------------------

    graph = build_transit_graph(
        db,
        verified_transfers_only=not include_unverified_transfers,
    )

    # --------------------------------------------------
    # 5. Generate candidate journeys
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

            # Every valid FIKA transit journey must contain
            # at least one actual dala-dala ride.
            if path_result["ride_connections"] < 1:
                continue

            instructions = generate_journey_instructions(
                graph,
                path_result,
            )

            # --------------------------------------------------
            # 6. Calculate access and egress walking metrics
            # --------------------------------------------------

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

            # --------------------------------------------------
            # 7. Calculate pedestrian routes between transfers
            # --------------------------------------------------

            transfer_walking_distance_m = 0.0
            transfer_walking_duration_seconds = 0.0

            transfer_walks = []
            all_transfers_routed = True

            for connection in path_result["connections"]:

                if connection["kind"] != "transfer":
                    continue

                from_stop_id = connection["from_stop_id"]
                to_stop_id = connection["to_stop_id"]

                from_node = graph.nodes[from_stop_id]
                to_node = graph.nodes[to_stop_id]

                recorded_distance = (
                    connection.get("walking_distance_m") or 0
                )

                try:
                    transfer_route = await provider.get_route(
                        origin=(
                            from_node["longitude"],
                            from_node["latitude"],
                        ),
                        destination=(
                            to_node["longitude"],
                            to_node["latitude"],
                        ),
                        costing=walking_config["costing"],
                    )

                    routed_distance_m = (
                        transfer_route["distance_km"] * 1000
                    )

                    routed_duration_seconds = (
                        transfer_route["duration_seconds"]
                    )

                    # A zero-distance route between distinct
                    # transfer records may indicate inaccurate
                    # or identical stop coordinates.
                    if (
                        routed_distance_m <= 0
                        and recorded_distance > 0
                    ):
                        effective_distance_m = recorded_distance
                        effective_duration_seconds = None
                        routing_status = "coordinate_mismatch"

                        all_transfers_routed = False

                    else:
                        effective_distance_m = (
                            routed_distance_m
                            if routed_distance_m > 0
                            else recorded_distance
                        )

                        effective_duration_seconds = (
                            routed_duration_seconds
                        )

                        routing_status = "success"

                    transfer_walking_distance_m += (
                        effective_distance_m
                    )

                    if effective_duration_seconds is not None:
                        transfer_walking_duration_seconds += (
                            effective_duration_seconds
                        )

                    transfer_walks.append({
                        "transfer_id": connection["transfer_id"],
                        "from_stop_id": from_stop_id,
                        "to_stop_id": to_stop_id,
                        "recorded_distance_m": recorded_distance,
                        "routed_distance_m": round(
                            routed_distance_m, 2
                        ),
                        "effective_distance_m": round(
                            effective_distance_m, 2
                        ),
                        "duration_seconds": (
                            effective_duration_seconds
                        ),
                        "geometry": transfer_route["geometry"],
                        "routing_status": routing_status,
                    })

                except ValhallaRoutingError:

                    # Preserve recorded distance if routing fails.
                    all_transfers_routed = False

                    transfer_walking_distance_m += (
                        recorded_distance
                    )

                    transfer_walks.append({
                        "transfer_id": connection["transfer_id"],
                        "from_stop_id": from_stop_id,
                        "to_stop_id": to_stop_id,
                        "recorded_distance_m": recorded_distance,
                        "routed_distance_m": None,
                        "effective_distance_m": recorded_distance,
                        "duration_seconds": None,
                        "geometry": None,
                        "routing_status": "unavailable",
                    })

            # --------------------------------------------------
            # 8. Calculate complete walking metrics
            # --------------------------------------------------

            total_walking_distance_m = (
                access_distance_m
                + egress_distance_m
                + transfer_walking_distance_m
            )

            # Do not report a complete duration if any transfer
            # walking route has an unknown duration.
            total_walking_duration_seconds = (
                access_seconds
                + egress_seconds
                + transfer_walking_duration_seconds
                if all_transfers_routed
                else None
            )

            # --------------------------------------------------
            # 9. Assemble journey result
            # --------------------------------------------------

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

                "transfer_walks": transfer_walks,

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
                    "access_walking_distance_m": round(
                        access_distance_m, 2
                    ),
                    "egress_walking_distance_m": round(
                        egress_distance_m, 2
                    ),
                    "transfer_walking_distance_m": round(
                        transfer_walking_distance_m, 2
                    ),
                    "total_walking_distance_m": round(
                        total_walking_distance_m, 2
                    ),
                    "access_egress_duration_seconds": (
                        access_seconds + egress_seconds
                    ),
                    "transfer_walking_duration_seconds": (
                        round(
                            transfer_walking_duration_seconds, 2
                        )
                        if all_transfers_routed
                        else None
                    ),
                    "total_walking_duration_seconds": (
                        round(
                            total_walking_duration_seconds, 2
                        )
                        if total_walking_duration_seconds is not None
                        else None
                    ),
                    "total_walking_duration_minutes": (
                        round(
                            total_walking_duration_seconds / 60, 2
                        )
                        if total_walking_duration_seconds is not None
                        else None
                    ),
                    "transfer_count": (
                        path_result["transfer_connections"]
                    ),
                },
            })

    # --------------------------------------------------
    # 10. Rank candidate journeys
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

    # --------------------------------------------------
    # 11. Return final journey-planning response
    # --------------------------------------------------

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

        "include_unverified_transfers": (
            include_unverified_transfers
        ),

        "ranking_method": (
            "Walking time, then transfer count, "
            "then walking distance."
        ),

        "estimation_notes": {
            "walking": (
                "Access and egress calculated using Valhalla "
                "pedestrian routing. Transfer walking routes are "
                "also calculated using Valhalla when available."
            ),
            "transfer_distance": (
                "Routed transfer distance is used when available. "
                "Recorded distance is used as a fallback."
            ),
            "transit_duration": "Not yet estimated.",
            "fare": "Not yet estimated.",
        },

        "total_journeys": len(ranked_journeys),
        "journeys": ranked_journeys,
    }
