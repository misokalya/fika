
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Route, Stop, RouteStop
from app.schemas import (
    RouteStopCreate,
    RouteStopUpdate,
    RouteStopResponse,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Route Stops"]
)


def get_active_route(db: Session, route_id: int) -> Route:
    route = db.get(Route, route_id)

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found."
        )

    if not route.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify an inactive route."
        )

    return route


def get_active_stop(db: Session, stop_id: int) -> Stop:
    stop = db.get(Stop, stop_id)

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop not found."
        )

    if not stop.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign an inactive stop."
        )

    return stop


def renumber_route_stops(
    db: Session,
    route_stops: list[RouteStop]
):
    """
    Safely assign consecutive sequence numbers starting at 1.

    Temporary positive sequence numbers avoid collisions with the
    unique (route_id, sequence) database constraint.
    """

    if not route_stops:
        return

    current_max = db.scalar(
        select(func.max(RouteStop.sequence)).where(
            RouteStop.route_id == route_stops[0].route_id
        )
    ) or 0

    temporary_start = current_max + len(route_stops) + 1000

    # Move every assignment to a unique temporary position.
    for index, route_stop in enumerate(route_stops, start=1):
        route_stop.sequence = temporary_start + index

    db.flush()

    # Assign final consecutive positions.
    for index, route_stop in enumerate(route_stops, start=1):
        route_stop.sequence = index

    db.flush()


@router.post(
    "/routes/{route_id}/stops",
    response_model=RouteStopResponse,
    status_code=status.HTTP_201_CREATED
)
def assign_stop_to_route(
    route_id: int,
    assignment_data: RouteStopCreate,
    db: Session = Depends(get_db)
):
    """Assign an active stop to an active route at a given position."""

    get_active_route(db, route_id)
    get_active_stop(db, assignment_data.stop_id)

    existing = db.scalar(
        select(RouteStop).where(
            RouteStop.route_id == route_id,
            RouteStop.stop_id == assignment_data.stop_id
        )
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This stop is already assigned to the route."
        )

    route_stops = list(
        db.scalars(
            select(RouteStop)
            .where(RouteStop.route_id == route_id)
            .order_by(RouteStop.sequence)
            .with_for_update()
        ).all()
    )

    if assignment_data.sequence > len(route_stops) + 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Sequence must be between 1 and {len(route_stops) + 1}."
        )

    # Give the new assignment a temporary unique sequence.
    temporary_sequence = (
        max((item.sequence for item in route_stops), default=0)
        + len(route_stops)
        + 1000
    )

    new_assignment = RouteStop(
        route_id=route_id,
        stop_id=assignment_data.stop_id,
        sequence=temporary_sequence,
        destination_board=assignment_data.destination_board,
    )

    # Insert at the requested position.
    route_stops.insert(
        assignment_data.sequence - 1,
        new_assignment
    )

    db.add(new_assignment)

    try:
        renumber_route_stops(db, route_stops)
        db.commit()
        db.refresh(new_assignment)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not assign this stop because of a database constraint conflict."
        )

    return new_assignment


@router.get(
    "/routes/{route_id}/stops",
    response_model=list[RouteStopResponse]
)
def list_route_stops(
    route_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve all stop assignments in route order."""

    route = db.get(Route, route_id)

    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found."
        )

    return db.scalars(
        select(RouteStop)
        .where(RouteStop.route_id == route_id)
        .order_by(RouteStop.sequence)
    ).all()


@router.get(
    "/route-stops/{route_stop_id}",
    response_model=RouteStopResponse
)
def get_route_stop(
    route_stop_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve an individual route-stop assignment."""

    assignment = db.get(RouteStop, route_stop_id)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route-stop assignment not found."
        )

    return assignment


@router.patch(
    "/route-stops/{route_stop_id}",
    response_model=RouteStopResponse
)
def update_route_stop(
    route_stop_id: int,
    update_data: RouteStopUpdate,
    db: Session = Depends(get_db)
):
    """Update destination-board text or move a stop to another position."""

    assignment = db.get(RouteStop, route_stop_id)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route-stop assignment not found."
        )

    get_active_route(db, assignment.route_id)

    changes = update_data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields were provided."
        )

    new_sequence = changes.pop("sequence", None)

    for field, value in changes.items():
        setattr(assignment, field, value)

    if new_sequence is not None:
        route_stops = list(
            db.scalars(
                select(RouteStop)
                .where(RouteStop.route_id == assignment.route_id)
                .order_by(RouteStop.sequence)
                .with_for_update()
            ).all()
        )

        if new_sequence > len(route_stops):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Sequence must be between 1 and {len(route_stops)}."
            )

        route_stops.remove(assignment)
        route_stops.insert(new_sequence - 1, assignment)

        try:
            renumber_route_stops(db, route_stops)
            db.commit()
            db.refresh(assignment)

        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not update the sequence because of a database constraint conflict."
            )

    else:
        try:
            db.commit()
            db.refresh(assignment)

        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not update this route-stop assignment."
            )

    return assignment


@router.delete("/route-stops/{route_stop_id}")
def remove_stop_from_route(
    route_stop_id: int,
    db: Session = Depends(get_db)
):
    """Remove a stop assignment without deleting the route or stop."""

    assignment = db.get(RouteStop, route_stop_id)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route-stop assignment not found."
        )

    route_id = assignment.route_id

    route_stops = list(
        db.scalars(
            select(RouteStop)
            .where(RouteStop.route_id == route_id)
            .order_by(RouteStop.sequence)
            .with_for_update()
        ).all()
    )

    route_stops.remove(assignment)

    try:
        db.delete(assignment)
        db.flush()

        renumber_route_stops(db, route_stops)

        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not remove this route-stop assignment."
        )

    return {
        "message": "Stop successfully removed from route.",
        "route_stop_id": route_stop_id,
        "route_id": route_id
    }
