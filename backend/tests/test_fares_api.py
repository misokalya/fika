
from datetime import datetime, timedelta, timezone

import pytest

from app.models import AuditLog, Fare, Route, User, UserRole
from app.services.auth.security import hash_password
from app.services.auth.tokens import create_access_token


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def create_test_user(db_session, role: UserRole) -> User:
    user = User(
        username=f"fare_{role.value}",
        email=f"fare_{role.value}@example.com",
        password_hash=hash_password("TestPassword123!"),
        role=role.value,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def auth_headers(user: User) -> dict:
    token = create_access_token(
        user_id=user.id,
        role=user.role,
    )
    return {"Authorization": f"Bearer {token}"}


def create_test_route(db_session) -> Route:
    route = Route(
        code="FARE-API-001",
        name="Fare API Test Route",
        is_active=True,
    )
    db_session.add(route)
    db_session.flush()
    return route


def create_test_fare(
    db_session,
    route_id: int,
    amount: float = 1000,
    verified: bool = False,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Fare:
    fare = Fare(
        route_id=route_id,
        amount_tzs=amount,
        effective_from=start or datetime.now(timezone.utc) - timedelta(days=1),
        effective_until=end,
        is_verified=verified,
    )
    db_session.add(fare)
    db_session.flush()
    return fare


@pytest.fixture
def fare_api_context(
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    route = create_test_route(db_session)

    passenger = create_test_user(db_session, UserRole.PASSENGER)
    operator = create_test_user(db_session, UserRole.OPERATOR)
    admin = create_test_user(db_session, UserRole.ADMIN)

    db_session.commit()

    return {
        "route": route,
        "passenger": passenger,
        "operator": operator,
        "admin": admin,
    }


# ---------------------------------------------------------------------
# Public current fare
# ---------------------------------------------------------------------

def test_passenger_can_get_current_verified_fare(
    db_client,
    db_session,
    fare_api_context,
):
    route = fare_api_context["route"]

    fare = create_test_fare(
        db_session,
        route.id,
        amount=1500,
        verified=True,
    )
    db_session.commit()

    response = db_client.get(
        f"/api/v1/fares/routes/{route.id}/current"
    )

    assert response.status_code == 200
    assert response.json()["id"] == fare.id
    assert response.json()["amount_tzs"] == 1500
    assert response.json()["is_verified"] is True


def test_current_fare_does_not_return_unverified_fare(
    db_client,
    db_session,
    fare_api_context,
):
    route = fare_api_context["route"]

    create_test_fare(
        db_session,
        route.id,
        amount=1500,
        verified=False,
    )
    db_session.commit()

    response = db_client.get(
        f"/api/v1/fares/routes/{route.id}/current"
    )

    assert response.status_code == 404


def test_current_fare_returns_404_for_unknown_route(db_client):
    response = db_client.get(
        "/api/v1/fares/routes/999999/current"
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------
# Fare history permissions
# ---------------------------------------------------------------------

def test_operator_can_view_route_fare_history(
    db_client,
    db_session,
    fare_api_context,
):
    route = fare_api_context["route"]
    operator = fare_api_context["operator"]

    create_test_fare(db_session, route.id, amount=1200)
    db_session.commit()

    response = db_client.get(
        f"/api/v1/fares/routes/{route.id}",
        headers=auth_headers(operator),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_passenger_cannot_view_fare_history(
    db_client,
    fare_api_context,
):
    route = fare_api_context["route"]
    passenger = fare_api_context["passenger"]

    response = db_client.get(
        f"/api/v1/fares/routes/{route.id}",
        headers=auth_headers(passenger),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------
# Fare creation
# ---------------------------------------------------------------------

def test_operator_can_create_unverified_fare(
    db_client,
    fare_api_context,
):
    operator = fare_api_context["operator"]
    route = fare_api_context["route"]

    payload = {
        "route_id": route.id,
        "amount_tzs": 1800,
        "effective_from": datetime.now(timezone.utc).isoformat(),
        "effective_until": None,
    }

    response = db_client.post(
        "/api/v1/fares/",
        json=payload,
        headers=auth_headers(operator),
    )

    assert response.status_code == 201

    data = response.json()
    assert data["route_id"] == route.id
    assert data["amount_tzs"] == 1800
    assert data["is_verified"] is False


def test_admin_can_create_unverified_fare(
    db_client,
    fare_api_context,
):
    admin = fare_api_context["admin"]
    route = fare_api_context["route"]

    payload = {
        "route_id": route.id,
        "amount_tzs": 2000,
        "effective_from": datetime.now(timezone.utc).isoformat(),
        "effective_until": None,
    }

    response = db_client.post(
        "/api/v1/fares/",
        json=payload,
        headers=auth_headers(admin),
    )

    assert response.status_code == 201
    assert response.json()["is_verified"] is False


def test_passenger_cannot_create_fare(
    db_client,
    fare_api_context,
):
    passenger = fare_api_context["passenger"]
    route = fare_api_context["route"]

    payload = {
        "route_id": route.id,
        "amount_tzs": 1800,
        "effective_from": datetime.now(timezone.utc).isoformat(),
        "effective_until": None,
    }

    response = db_client.post(
        "/api/v1/fares/",
        json=payload,
        headers=auth_headers(passenger),
    )

    assert response.status_code == 403


def test_operator_cannot_create_overlapping_fare(
    db_client,
    db_session,
    fare_api_context,
):
    operator = fare_api_context["operator"]
    route = fare_api_context["route"]

    start = datetime.now(timezone.utc) - timedelta(days=1)

    create_test_fare(
        db_session,
        route.id,
        amount=1000,
        start=start,
        end=None,
    )
    db_session.commit()

    payload = {
        "route_id": route.id,
        "amount_tzs": 1500,
        "effective_from": (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(),
        "effective_until": None,
    }

    response = db_client.post(
        "/api/v1/fares/",
        json=payload,
        headers=auth_headers(operator),
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------
# Fare updates
# ---------------------------------------------------------------------

def test_operator_can_update_fare(
    db_client,
    db_session,
    fare_api_context,
):
    operator = fare_api_context["operator"]
    route = fare_api_context["route"]

    fare = create_test_fare(
        db_session,
        route.id,
        amount=1000,
    )
    db_session.commit()

    response = db_client.patch(
        f"/api/v1/fares/{fare.id}",
        json={"amount_tzs": 1400},
        headers=auth_headers(operator),
    )

    assert response.status_code == 200
    assert response.json()["amount_tzs"] == 1400
    assert response.json()["is_verified"] is False


def test_updating_verified_fare_resets_verification(
    db_client,
    db_session,
    fare_api_context,
):
    operator = fare_api_context["operator"]
    route = fare_api_context["route"]

    fare = create_test_fare(
        db_session,
        route.id,
        amount=1000,
        verified=True,
    )
    db_session.commit()

    response = db_client.patch(
        f"/api/v1/fares/{fare.id}",
        json={"amount_tzs": 1600},
        headers=auth_headers(operator),
    )

    assert response.status_code == 200
    assert response.json()["amount_tzs"] == 1600
    assert response.json()["is_verified"] is False


def test_passenger_cannot_update_fare(
    db_client,
    db_session,
    fare_api_context,
):
    passenger = fare_api_context["passenger"]
    route = fare_api_context["route"]

    fare = create_test_fare(db_session, route.id)
    db_session.commit()

    response = db_client.patch(
        f"/api/v1/fares/{fare.id}",
        json={"amount_tzs": 2000},
        headers=auth_headers(passenger),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------
# Fare verification
# ---------------------------------------------------------------------

def test_admin_can_verify_fare(
    db_client,
    db_session,
    fare_api_context,
):
    admin = fare_api_context["admin"]
    route = fare_api_context["route"]

    fare = create_test_fare(
        db_session,
        route.id,
        amount=1500,
        verified=False,
    )
    db_session.commit()

    response = db_client.post(
        f"/api/v1/fares/{fare.id}/verify",
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.json()["is_verified"] is True


def test_operator_cannot_verify_fare(
    db_client,
    db_session,
    fare_api_context,
):
    operator = fare_api_context["operator"]
    route = fare_api_context["route"]

    fare = create_test_fare(db_session, route.id)
    db_session.commit()

    response = db_client.post(
        f"/api/v1/fares/{fare.id}/verify",
        headers=auth_headers(operator),
    )

    assert response.status_code == 403


def test_passenger_cannot_verify_fare(
    db_client,
    db_session,
    fare_api_context,
):
    passenger = fare_api_context["passenger"]
    route = fare_api_context["route"]

    fare = create_test_fare(db_session, route.id)
    db_session.commit()

    response = db_client.post(
        f"/api/v1/fares/{fare.id}/verify",
        headers=auth_headers(passenger),
    )

    assert response.status_code == 403


def test_fare_verification_is_recorded_in_audit_log(
    db_client,
    db_session,
    fare_api_context,
):
    admin = fare_api_context["admin"]
    route = fare_api_context["route"]

    fare = create_test_fare(db_session, route.id)
    db_session.commit()

    response = db_client.post(
        f"/api/v1/fares/{fare.id}/verify",
        headers=auth_headers(admin),
    )

    assert response.status_code == 200

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "FARE_VERIFIED",
            AuditLog.entity_id == fare.id,
        )
        .first()
    )

    assert audit is not None
    assert audit.entity_type == "fare"
