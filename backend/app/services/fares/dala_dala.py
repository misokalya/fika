
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Fare


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def ensure_no_overlapping_fare(
    db: Session,
    route_id: int,
    effective_from: datetime,
    effective_until: datetime | None,
    exclude_fare_id: int | None = None,
) -> None:
    """
    Reject overlapping fare periods for the same route.

    Periods are interpreted as:
        [effective_from, effective_until)

    A None effective_until represents an open-ended period.
    """

    _validate_aware_datetime(effective_from, "effective_from")

    if effective_until is not None:
        _validate_aware_datetime(effective_until, "effective_until")

        if effective_until <= effective_from:
            raise ValueError(
                "effective_until must be later than effective_from."
            )

    # Existing fare starts before the proposed period ends.
    starts_before_new_end = (
        True
        if effective_until is None
        else Fare.effective_from < effective_until
    )

    # Existing fare ends after the proposed period starts,
    # or has no end date.
    ends_after_new_start = or_(
        Fare.effective_until.is_(None),
        Fare.effective_until > effective_from,
    )

    statement = select(Fare.id).where(
        Fare.route_id == route_id,
        starts_before_new_end,
        ends_after_new_start,
    )

    if exclude_fare_id is not None:
        statement = statement.where(Fare.id != exclude_fare_id)

    overlapping_fare_id = db.scalar(statement.limit(1))

    if overlapping_fare_id is not None:
        raise ValueError(
            "This fare period overlaps another fare period "
            "for the same route."
        )


def get_effective_route_fare(
    db: Session,
    route_id: int,
    at: datetime | None = None,
    verified_only: bool = True,
) -> Fare | None:
    """
    Return the fare effective for a route at a given time.

    By default, only verified fares are considered.
    The effective period is start-inclusive and end-exclusive.
    """

    effective_at = at or _utc_now()
    _validate_aware_datetime(effective_at, "at")

    conditions = [
        Fare.route_id == route_id,
        Fare.effective_from <= effective_at,
        or_(
            Fare.effective_until.is_(None),
            Fare.effective_until > effective_at,
        ),
    ]

    if verified_only:
        conditions.append(Fare.is_verified.is_(True))

    statement = (
        select(Fare)
        .where(*conditions)
        .order_by(Fare.effective_from.desc(), Fare.id.desc())
        .limit(1)
    )

    return db.scalar(statement)


def list_route_fares(
    db: Session,
    route_id: int,
    verified_only: bool = False,
) -> list[Fare]:
    """Return fare history for a route, newest first."""

    conditions = [Fare.route_id == route_id]

    if verified_only:
        conditions.append(Fare.is_verified.is_(True))

    statement = (
        select(Fare)
        .where(*conditions)
        .order_by(Fare.effective_from.desc(), Fare.id.desc())
    )

    return list(db.scalars(statement).all())
