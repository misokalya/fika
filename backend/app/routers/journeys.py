
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Stop
from app.schemas import JourneyPlanRequest, JourneyPlanResponse

from app.services.transit.graph import build_transit_graph
from app.services.transit.pathfinder import (
    find_transit_path,
    TransitPathNotFoundError,
)
from app.services.transit.instructions import generate_journey_instructions


router = APIRouter(
    prefix="/api/v1/journeys",
    tags=["Journeys"],
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
