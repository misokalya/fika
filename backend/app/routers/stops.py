
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape

from app.dependencies import get_db
from app.models import Stop, UserRole
from app.schemas import StopCreate, StopUpdate, StopResponse
from app.services.auth.dependencies import require_roles


router = APIRouter(
    prefix="/api/v1/stops",
    tags=["Stops"]
)


# Only operators and administrators can modify official stop data.
stop_managers = require_roles(
    UserRole.OPERATOR,
    UserRole.ADMIN
)


def stop_to_response(stop: Stop) -> StopResponse:
    """Convert a Stop database model into an API response."""

    geometry = to_shape(stop.location)

    return StopResponse(
        id=stop.id,
        name=stop.name,
        description=stop.description,
        stop_type=stop.stop_type,
        latitude=geometry.y,
        longitude=geometry.x,
        is_verified=stop.is_verified,
        is_active=stop.is_active,
        created_at=stop.created_at,
    )


@router.post(
    "",
    response_model=StopResponse,
    status_code=status.HTTP_201_CREATED
)
def create_stop(
    stop_data: StopCreate,
    db: Session = Depends(get_db),
    current_user=Depends(stop_managers)
):
    """Create a new transport stop. Requires operator or admin access."""

    stop = Stop(
        name=stop_data.name,
        description=stop_data.description,
        stop_type=stop_data.stop_type,
        location=WKTElement(
            f"POINT({stop_data.longitude} {stop_data.latitude})",
            srid=4326
        ),
        is_verified=stop_data.is_verified,
        is_active=stop_data.is_active,
    )

    db.add(stop)
    db.commit()
    db.refresh(stop)

    return stop_to_response(stop)


@router.get(
    "",
    response_model=list[StopResponse]
)
def list_stops(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    active_only: bool = True,
    verified_only: bool = False,
    db: Session = Depends(get_db)
):
    """List transport stops with optional filters. Publicly accessible."""

    statement = select(Stop)

    if active_only:
        statement = statement.where(Stop.is_active.is_(True))

    if verified_only:
        statement = statement.where(Stop.is_verified.is_(True))

    statement = statement.offset(skip).limit(limit)

    stops = db.scalars(statement).all()

    return [stop_to_response(stop) for stop in stops]


@router.get(
    "/{stop_id}",
    response_model=StopResponse
)
def get_stop(
    stop_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve an individual stop. Publicly accessible."""

    stop = db.get(Stop, stop_id)

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop not found."
        )

    return stop_to_response(stop)


@router.patch(
    "/{stop_id}",
    response_model=StopResponse
)
def update_stop(
    stop_id: int,
    stop_data: StopUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(stop_managers)
):
    """Update stop information. Requires operator or admin access."""

    stop = db.get(Stop, stop_id)

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop not found."
        )

    update_data = stop_data.model_dump(exclude_unset=True)

    latitude = update_data.pop("latitude", None)
    longitude = update_data.pop("longitude", None)

    for field, value in update_data.items():
        setattr(stop, field, value)

    if latitude is not None and longitude is not None:
        stop.location = WKTElement(
            f"POINT({longitude} {latitude})",
            srid=4326
        )

    db.commit()
    db.refresh(stop)

    return stop_to_response(stop)


@router.delete(
    "/{stop_id}"
)
def deactivate_stop(
    stop_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(stop_managers)
):
    """Soft-delete a stop. Requires operator or admin access."""

    stop = db.get(Stop, stop_id)

    if not stop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stop not found."
        )

    if not stop.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stop is already inactive."
        )

    stop.is_active = False

    db.commit()

    return {
        "message": "Stop successfully deactivated.",
        "stop_id": stop.id
    }
