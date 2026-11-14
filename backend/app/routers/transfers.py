
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import get_db
from app.models import Route, Stop, RouteStop, Transfer
from app.schemas import (
    TransferCreate,
    TransferUpdate,
    TransferResponse,
)


router = APIRouter(
    prefix="/api/v1/transfers",
    tags=["Transfers"],
)


def get_active_route(db: Session, route_id: int) -> Route:
    route = db.get(Route, route_id)

    if route is None or not route.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active route with ID {route_id} not found",
        )

    return route


def get_active_stop(db: Session, stop_id: int) -> Stop:
    stop = db.get(Stop, stop_id)

    if stop is None or not stop.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active stop with ID {stop_id} not found",
        )

    return stop


def validate_stop_belongs_to_route(
    db: Session,
    route_id: int,
    stop_id: int,
):
    assignment = db.scalar(
        select(RouteStop).where(
            RouteStop.route_id == route_id,
            RouteStop.stop_id == stop_id,
        )
    )

    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Stop {stop_id} is not assigned to "
                f"route {route_id}"
            ),
        )


def validate_transfer_relationships(
    db: Session,
    from_route_id: int,
    to_route_id: int,
    from_stop_id: int,
    to_stop_id: int,
):
    if from_route_id == to_route_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A transfer must connect two different routes",
        )

    get_active_route(db, from_route_id)
    get_active_route(db, to_route_id)

    get_active_stop(db, from_stop_id)
    get_active_stop(db, to_stop_id)

    validate_stop_belongs_to_route(
        db,
        from_route_id,
        from_stop_id,
    )

    validate_stop_belongs_to_route(
        db,
        to_route_id,
        to_stop_id,
    )


@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    transfer_data: TransferCreate,
    db: Session = Depends(get_db),
):
    validate_transfer_relationships(
        db,
        transfer_data.from_route_id,
        transfer_data.to_route_id,
        transfer_data.from_stop_id,
        transfer_data.to_stop_id,
    )

    transfer = Transfer(**transfer_data.model_dump())

    db.add(transfer)
    db.commit()
    db.refresh(transfer)

    return transfer


@router.get(
    "",
    response_model=list[TransferResponse],
)
def list_transfers(
    from_route_id: int | None = None,
    to_route_id: int | None = None,
    verified_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="skip cannot be negative",
        )

    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 500",
        )

    query = select(Transfer)

    if from_route_id is not None:
        query = query.where(
            Transfer.from_route_id == from_route_id
        )

    if to_route_id is not None:
        query = query.where(
            Transfer.to_route_id == to_route_id
        )

    if verified_only:
        query = query.where(Transfer.is_verified.is_(True))

    query = query.order_by(Transfer.id).offset(skip).limit(limit)

    return db.scalars(query).all()


@router.get(
    "/{transfer_id}",
    response_model=TransferResponse,
)
def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
):
    transfer = db.get(Transfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found",
        )

    return transfer


@router.patch(
    "/{transfer_id}",
    response_model=TransferResponse,
)
def update_transfer(
    transfer_id: int,
    transfer_data: TransferUpdate,
    db: Session = Depends(get_db),
):
    transfer = db.get(Transfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found",
        )

    update_data = transfer_data.model_dump(exclude_unset=True)

    # Build the complete resulting relationship before validating.
    from_route_id = update_data.get(
        "from_route_id", transfer.from_route_id
    )
    to_route_id = update_data.get(
        "to_route_id", transfer.to_route_id
    )
    from_stop_id = update_data.get(
        "from_stop_id", transfer.from_stop_id
    )
    to_stop_id = update_data.get(
        "to_stop_id", transfer.to_stop_id
    )

    if any(
        value is None
        for value in (
            from_route_id,
            to_route_id,
            from_stop_id,
            to_stop_id,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer relationship fields cannot be null",
        )

    validate_transfer_relationships(
        db,
        from_route_id,
        to_route_id,
        from_stop_id,
        to_stop_id,
    )

    for field, value in update_data.items():
        setattr(transfer, field, value)

    db.commit()
    db.refresh(transfer)

    return transfer


@router.delete(
    "/{transfer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
):
    transfer = db.get(Transfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found",
        )

    db.delete(transfer)
    db.commit()

    return None
