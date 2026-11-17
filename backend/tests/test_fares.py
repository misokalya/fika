
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Fare, Route
from app.services.fares.dala_dala import (
    ensure_no_overlapping_fare,
    get_effective_route_fare,
    list_route_fares,
)


def make_route(db_session):
    route = Route(
        code="FARE-TEST-001",
        name="Fare Test Route",
        is_active=True,
    )
    db_session.add(route)
    db_session.flush()
    return route


def make_fare(
    db_session,
    route_id,
    start,
    end=None,
    amount=500,
    verified=True,
):
    fare = Fare(
        route_id=route_id,
        amount_tzs=amount,
        effective_from=start,
        effective_until=end,
        is_verified=verified,
    )
    db_session.add(fare)
    db_session.flush()
    return fare


@pytest.fixture
def fare_route(db_session, clean_transport_tables):
    return make_route(db_session)


def test_returns_verified_effective_fare(db_session, fare_route):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    fare = make_fare(
        db_session,
        fare_route.id,
        now - timedelta(days=10),
        amount=700,
        verified=True,
    )

    result = get_effective_route_fare(
        db_session,
        fare_route.id,
        at=now,
    )

    assert result is not None
    assert result.id == fare.id
    assert result.amount_tzs == 700


def test_excludes_unverified_fare_by_default(db_session, fare_route):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    make_fare(
        db_session,
        fare_route.id,
        now - timedelta(days=1),
        amount=700,
        verified=False,
    )

    result = get_effective_route_fare(
        db_session,
        fare_route.id,
        at=now,
    )

    assert result is None


def test_can_explicitly_include_unverified_fare(db_session, fare_route):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    fare = make_fare(
        db_session,
        fare_route.id,
        now - timedelta(days=1),
        amount=700,
        verified=False,
    )

    result = get_effective_route_fare(
        db_session,
        fare_route.id,
        at=now,
        verified_only=False,
    )

    assert result is not None
    assert result.id == fare.id


def test_excludes_future_fare(db_session, fare_route):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    make_fare(
        db_session,
        fare_route.id,
        now + timedelta(days=1),
        amount=900,
        verified=True,
    )

    result = get_effective_route_fare(
        db_session,
        fare_route.id,
        at=now,
    )

    assert result is None


def test_excludes_expired_fare(db_session, fare_route):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    make_fare(
        db_session,
        fare_route.id,
        now - timedelta(days=10),
        end=now - timedelta(days=1),
        amount=700,
        verified=True,
    )

    result = get_effective_route_fare(
        db_session,
        fare_route.id,
        at=now,
    )

    assert result is None


def test_effective_period_includes_start(db_session, fare_route):
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)

    fare = make_fare(
        db_session,
        fare_route.id,
        start,
        amount=700,
        verified=True,
    )

    result = get_effective_route_fare(
        db_session,
        fare_route.id,
        at=start,
    )

    assert result is not None
    assert result.id == fare.id


def test_effective_period_excludes_end(db_session, fare_route):
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=30)

    make_fare(
        db_session,
        fare_route.id,
        start,
        end=end,
        amount=700,
        verified=True,
    )

    result = get_effective_route_fare(
        db_session,
        fare_route.id,
        at=end,
    )

    assert result is None


def test_lists_route_fare_history_newest_first(db_session, fare_route):
    first_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second_start = datetime(2026, 2, 1, tzinfo=timezone.utc)

    first = make_fare(
        db_session,
        fare_route.id,
        first_start,
        amount=500,
    )

    second = make_fare(
        db_session,
        fare_route.id,
        second_start,
        amount=700,
    )

    results = list_route_fares(db_session, fare_route.id)

    assert [fare.id for fare in results] == [second.id, first.id]


def test_rejects_overlapping_fare_periods(db_session, fare_route):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    make_fare(
        db_session,
        fare_route.id,
        start,
        end=start + timedelta(days=30),
    )

    with pytest.raises(ValueError, match="overlaps"):
        ensure_no_overlapping_fare(
            db_session,
            fare_route.id,
            start + timedelta(days=15),
            start + timedelta(days=45),
        )


def test_allows_adjacent_fare_periods(db_session, fare_route):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    boundary = start + timedelta(days=30)

    make_fare(
        db_session,
        fare_route.id,
        start,
        end=boundary,
    )

    # The next fare starts exactly when the previous one ends.
    ensure_no_overlapping_fare(
        db_session,
        fare_route.id,
        boundary,
        None,
    )


def test_rejects_naive_datetime(db_session, fare_route):
    with pytest.raises(ValueError, match="timezone-aware"):
        get_effective_route_fare(
            db_session,
            fare_route.id,
            at=datetime(2026, 6, 1),
        )
