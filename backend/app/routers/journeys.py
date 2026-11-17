
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import (
    JourneyObservation,
    Route,
    RouteStop,
    Stop,
    UserRole,
)
from app.schemas import (
    JourneyPlanRequest,
    JourneyPlanResponse,
    CoordinateJourneyPlanRequest,
    JourneyObservationCreate,
)

from app.services.auth.dependencies import require_roles
from app.services.transit.graph import build_transit_graph
from app.services.transit.pathfinder import (
    find_transit_path,
    TransitPathNotFoundError,
)
from app.services.transit.instructions import generate_journey_instructions
from app.services.journey.planner import plan_coordinate_journey


router = APIRouter(
    prefix="/api/v1/journeys",
    tags=["Journeys"],
)


observation_submitters = require_roles(
    UserRole.FIELD_RESEARCHER,
    UserRole.OPERATOR,
    UserRole.ADMIN,
)


@router.post("/plan", response_model=JourneyPlanResponse)
def plan_journey(
    request: JourneyPlanRequest,
    db: Session = Depends(get_db),
):
    # Confirm that both stops exist and are active.
    origin = db.get(Stop, request.origin_stop_id)
    destination = db.get(Stop, request.destination_stop_id)

    if origin is None or not origin.is_active:
        raise HTTPException(
            status_code=404,
            detail="Origin stop not found or inactive.",
        )

    if destination is None or not destination.is_active:
        raise HTTPException(
            status_code=404,
            detail="Destination stop not found or inactive.",
        )

    # Build the transit graph using the requested transfer policy.
    graph = build_transit_graph(
        db,
        verified_transfers_only=not request.include_unverified_transfers,
    )

    # Confirm that both stops are connected to active transit routes.
    if request.origin_stop_id not in graph:
        raise HTTPException(
            status_code=422,
            detail="Origin stop is not currently connected to an active transit route.",
        )

    if request.destination_stop_id not in graph:
        raise HTTPException(
            status_code=422,
            detail="Destination stop is not currently connected to an active transit route.",
        )

    # Find the transit path.
    try:
        path_result = find_transit_path(
            graph,
            request.origin_stop_id,
            request.destination_stop_id,
        )
    except TransitPathNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="No transit journey was found between these stops.",
        )

    # Convert the path into passenger-friendly instructions.
    instructions = generate_journey_instructions(
        graph,
        path_result,
    )

    return {
        "status": "success",
        "origin_stop_id": request.origin_stop_id,
        "destination_stop_id": request.destination_stop_id,
        "include_unverified_transfers": request.include_unverified_transfers,
        "path": path_result,
        "instructions": instructions,
    }


@router.post("/plan-coordinates")
async def plan_coordinates(
    request: CoordinateJourneyPlanRequest,
    db: Session = Depends(get_db),
):
    origin = (
        request.origin_longitude,
        request.origin_latitude,
    )

    destination = (
        request.destination_longitude,
        request.destination_latitude,
    )

    result = await plan_coordinate_journey(
        db=db,
        origin=origin,
        destination=destination,
        radius_m=request.radius_m,
        candidate_limit=request.candidate_limit,
        include_unverified_transfers=(
            request.include_unverified_transfers
        ),
    )

    return result


@router.post("/observations", status_code=201)
def create_journey_observation(
    request: JourneyObservationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(observation_submitters),
):
    # Confirm that the route exists and is active.
    route = db.get(Route, request.route_id)

    if route is None or not route.is_active:
        raise HTTPException(
            status_code=404,
            detail="Route not found or inactive.",
        )

    # Confirm that both stops exist and are active.
    from_stop = db.get(Stop, request.from_stop_id)
    to_stop = db.get(Stop, request.to_stop_id)

    if from_stop is None or not from_stop.is_active:
        raise HTTPException(
            status_code=404,
            detail="Starting stop not found or inactive.",
        )

    if to_stop is None or not to_stop.is_active:
        raise HTTPException(
            status_code=404,
            detail="Ending stop not found or inactive.",
        )

    # Retrieve the positions of both stops on this route.
    route_stops = (
        db.query(RouteStop)
        .filter(
            RouteStop.route_id == request.route_id,
            RouteStop.stop_id.in_([
                request.from_stop_id,
                request.to_stop_id,
            ]),
        )
        .all()
    )

    stop_sequences = {
        route_stop.stop_id: route_stop.sequence
        for route_stop in route_stops
    }

    if request.from_stop_id not in stop_sequences:
        raise HTTPException(
            status_code=422,
            detail="Starting stop does not belong to the selected route.",
        )

    if request.to_stop_id not in stop_sequences:
        raise HTTPException(
            status_code=422,
            detail="Ending stop does not belong to the selected route.",
        )

    if (
        stop_sequences[request.from_stop_id]
        >= stop_sequences[request.to_stop_id]
    ):
        raise HTTPException(
            status_code=422,
            detail="Starting stop must occur before ending stop on the selected route.",
        )

    # Create an unverified field observation.
    observation = JourneyObservation(
        route_id=request.route_id,
        from_stop_id=request.from_stop_id,
        to_stop_id=request.to_stop_id,
        departure_time=request.departure_time,
        duration_seconds=request.duration_seconds,
        wait_seconds=request.wait_seconds,
        weekday=request.departure_time.weekday(),
        source="field",
        is_verified=False,
        notes=request.notes,
    )

    try:
        db.add(observation)
        db.commit()
        db.refresh(observation)
    except Exception:
        db.rollback()
        raise

    return {
        "status": "success",
        "message": "Journey observation recorded successfully.",
        "observation": {
            "id": observation.id,
            "route_id": observation.route_id,
            "from_stop_id": observation.from_stop_id,
            "to_stop_id": observation.to_stop_id,
            "departure_time": observation.departure_time,
            "duration_seconds": observation.duration_seconds,
            "wait_seconds": observation.wait_seconds,
            "weekday": observation.weekday,
            "source": observation.source,
            "is_verified": observation.is_verified,
            "notes": observation.notes,
        },
    }
