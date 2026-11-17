
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.services.auth.dependencies import require_roles
from app.models import AuditLog, Fare, Route, User, UserRole
from app.schemas import FareCreate, FareResponse, FareUpdate
from app.services.fares.dala_dala import (
    ensure_no_overlapping_fare,
    get_effective_route_fare,
    list_route_fares,
)

router = APIRouter(
    prefix="/api/v1/fares",
    tags=["Fares"],
)

fare_managers = require_roles(UserRole.OPERATOR, UserRole.ADMIN)
admin_only = require_roles(UserRole.ADMIN)


def get_active_route_or_404(db: Session, route_id: int) -> Route:
    route = db.get(Route, route_id)

    if route is None or not route.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active route not found.",
        )

    return route


def get_fare_or_404(db: Session, fare_id: int) -> Fare:
    fare = db.get(Fare, fare_id)

    if fare is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fare not found.",
        )

    return fare


def write_fare_audit(
    db: Session,
    user: User,
    action: str,
    fare: Fare,
    details: dict,
) -> None:
    db.add(
        AuditLog(
            actor=user.username,
            action=action,
            entity_type="fare",
            entity_id=fare.id,
            details=details,
        )
    )


@router.get(
    "/routes/{route_id}/current",
    response_model=FareResponse,
)
def get_current_fare(
    route_id: int,
    db: Session = Depends(get_db),
):
    get_active_route_or_404(db, route_id)

    fare = get_effective_route_fare(
        db=db,
        route_id=route_id,
        at=datetime.now(timezone.utc),
        verified_only=True,
    )

    if fare is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No verified fare is currently available for this route.",
        )

    return fare


@router.get(
    "/routes/{route_id}",
    response_model=list[FareResponse],
)
def get_route_fare_history(
    route_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(fare_managers),
):
    get_active_route_or_404(db, route_id)

    return list_route_fares(
        db=db,
        route_id=route_id,
        verified_only=False,
    )


@router.post(
    "/",
    response_model=FareResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_fare(
    payload: FareCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(fare_managers),
):
    route = get_active_route_or_404(db, payload.route_id)

    try:
        ensure_no_overlapping_fare(
            db=db,
            route_id=route.id,
            effective_from=payload.effective_from,
            effective_until=payload.effective_until,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    fare = Fare(
        route_id=route.id,
        amount_tzs=payload.amount_tzs,
        effective_from=payload.effective_from,
        effective_until=payload.effective_until,
        is_verified=False,
    )

    db.add(fare)
    db.flush()

    write_fare_audit(
        db=db,
        user=current_user,
        action="FARE_CREATED",
        fare=fare,
        details={
            "route_id": fare.route_id,
            "amount_tzs": fare.amount_tzs,
            "effective_from": fare.effective_from.isoformat(),
            "effective_until": (
                fare.effective_until.isoformat()
                if fare.effective_until
                else None
            ),
            "is_verified": False,
        },
    )

    db.commit()
    db.refresh(fare)

    return fare


@router.patch(
    "/{fare_id}",
    response_model=FareResponse,
)
def update_fare(
    fare_id: int,
    payload: FareUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(fare_managers),
):
    fare = get_fare_or_404(db, fare_id)
    get_active_route_or_404(db, fare.route_id)

    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided.",
        )

    new_amount = changes.get("amount_tzs", fare.amount_tzs)
    new_start = changes.get("effective_from", fare.effective_from)
    new_end = changes.get("effective_until", fare.effective_until)

    try:
        ensure_no_overlapping_fare(
            db=db,
            route_id=fare.route_id,
            effective_from=new_start,
            effective_until=new_end,
            exclude_fare_id=fare.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # Editing a verified fare invalidates its previous verification.
    was_verified = fare.is_verified

    fare.amount_tzs = new_amount
    fare.effective_from = new_start
    fare.effective_until = new_end

    if was_verified:
        fare.is_verified = False

    write_fare_audit(
        db=db,
        user=current_user,
        action="FARE_UPDATED",
        fare=fare,
        details={
            "changes": {
                key: (
                    value.isoformat()
                    if isinstance(value, datetime)
                    else value
                )
                for key, value in changes.items()
            },
            "previously_verified": was_verified,
            "verification_reset": was_verified,
        },
    )

    db.commit()
    db.refresh(fare)

    return fare


@router.post(
    "/{fare_id}/verify",
    response_model=FareResponse,
)
def verify_fare(
    fare_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    fare = get_fare_or_404(db, fare_id)
    get_active_route_or_404(db, fare.route_id)

    if fare.is_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Fare is already verified.",
        )

    try:
        ensure_no_overlapping_fare(
            db=db,
            route_id=fare.route_id,
            effective_from=fare.effective_from,
            effective_until=fare.effective_until,
            exclude_fare_id=fare.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    fare.is_verified = True

    write_fare_audit(
        db=db,
        user=current_user,
        action="FARE_VERIFIED",
        fare=fare,
        details={
            "route_id": fare.route_id,
            "amount_tzs": fare.amount_tzs,
        },
    )

    db.commit()
    db.refresh(fare)

    return fare
