
from datetime import datetime, timezone

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.models import (
    AuditLog,
    JourneyObservation,
    Route,
    RouteStop,
    Stop,
    User,
    UserRole,
)
from app.services.auth.security import hash_password


# ---------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------

def create_user(
    db_session,
    username,
    email,
    role=UserRole.PASSENGER.value,
):
    user = User(
        username=username,
        email=email,
        password_hash=hash_password("TestPassword123!"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def get_token(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "TestPassword123!",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def create_route(db_session, code="ARU-TEST-001"):
    route = Route(
        code=code,
        name="FIKA Test Route",
        description="Automated RBAC test route",
        is_active=True,
    )
    db_session.add(route)
    db_session.commit()
    db_session.refresh(route)
    return route


def create_stop(db_session, name):
    stop = Stop(
        name=name,
        description="Automated test stop",
        stop_type="formal",
        location=WKTElement(
            "POINT(36.69438 -3.37238)",
            srid=4326,
        ),
        is_verified=True,
        is_active=True,
    )
    db_session.add(stop)
    db_session.commit()
    db_session.refresh(stop)
    return stop


def create_route_with_two_stops(db_session):
    route = create_route(db_session)

    first_stop = create_stop(db_session, "FIKA Test Stop A")
    second_stop = create_stop(db_session, "FIKA Test Stop B")

    db_session.add_all([
        RouteStop(
            route_id=route.id,
            stop_id=first_stop.id,
            sequence=1,
        ),
        RouteStop(
            route_id=route.id,
            stop_id=second_stop.id,
            sequence=2,
        ),
    ])
    db_session.commit()

    return route, first_stop, second_stop


def observation_payload(route, first_stop, second_stop):
    return {
        "route_id": route.id,
        "from_stop_id": first_stop.id,
        "to_stop_id": second_stop.id,
        "departure_time": "2026-11-17T08:30:00Z",
        "duration_seconds": 420,
        "wait_seconds": 60,
        "notes": "Automated observation test",
    }


# ---------------------------------------------------------
# Route management permissions
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "role",
    [
        UserRole.OPERATOR.value,
        UserRole.ADMIN.value,
    ],
)
def test_operator_and_admin_can_create_route(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
    role,
):
    user = create_user(
        db_session,
        username=f"{role}_user",
        email=f"{role}@example.com",
        role=role,
    )
    token = get_token(db_client, user.email)

    response = db_client.post(
        "/api/v1/routes",
        headers=headers(token),
        json={
            "code": f"ARU-{role.upper()}",
            "name": "Authorized Test Route",
            "description": "Created by authorized user",
            "is_active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["code"] == f"ARU-{role.upper()}"


@pytest.mark.parametrize(
    "role",
    [
        UserRole.PASSENGER.value,
        UserRole.FIELD_RESEARCHER.value,
    ],
)
def test_passenger_and_researcher_cannot_create_route(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
    role,
):
    user = create_user(
        db_session,
        username=f"{role}_user",
        email=f"{role}@example.com",
        role=role,
    )
    token = get_token(db_client, user.email)

    response = db_client.post(
        "/api/v1/routes",
        headers=headers(token),
        json={
            "code": f"ARU-{role.upper()}",
            "name": "Unauthorized Test Route",
        },
    )

    assert response.status_code == 403


def test_operator_can_update_and_deactivate_route(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "operator",
        "operator@example.com",
        UserRole.OPERATOR.value,
    )
    route = create_route(db_session)
    token = get_token(db_client, user.email)

    update_response = db_client.patch(
        f"/api/v1/routes/{route.id}",
        headers=headers(token),
        json={"name": "Updated Test Route"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Test Route"

    deactivate_response = db_client.delete(
        f"/api/v1/routes/{route.id}",
        headers=headers(token),
    )

    assert deactivate_response.status_code == 200

    db_session.expire_all()
    updated_route = db_session.get(Route, route.id)
    assert updated_route.is_active is False


def test_passenger_cannot_update_route(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "passenger",
        "passenger@example.com",
    )
    route = create_route(db_session)
    token = get_token(db_client, user.email)

    response = db_client.patch(
        f"/api/v1/routes/{route.id}",
        headers=headers(token),
        json={"name": "Unauthorized Change"},
    )

    assert response.status_code == 403


# ---------------------------------------------------------
# Journey observation permissions
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "role",
    [
        UserRole.FIELD_RESEARCHER.value,
        UserRole.OPERATOR.value,
        UserRole.ADMIN.value,
    ],
)
def test_authorized_roles_can_submit_observation(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
    role,
):
    user = create_user(
        db_session,
        f"{role}_user",
        f"{role}@example.com",
        role,
    )

    route, first_stop, second_stop = create_route_with_two_stops(
        db_session
    )

    token = get_token(db_client, user.email)

    response = db_client.post(
        "/api/v1/journeys/observations",
        headers=headers(token),
        json=observation_payload(route, first_stop, second_stop),
    )

    assert response.status_code == 201

    data = response.json()
    observation_data = data["observation"]

    assert data["status"] == "success"
    assert observation_data["route_id"] == route.id
    assert observation_data["from_stop_id"] == first_stop.id
    assert observation_data["to_stop_id"] == second_stop.id
    assert observation_data["duration_seconds"] == 420
    assert observation_data["wait_seconds"] == 60
    assert observation_data["source"] == "field"
    assert observation_data["is_verified"] is False


def test_passenger_cannot_submit_observation(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "passenger",
        "passenger@example.com",
    )

    route, first_stop, second_stop = create_route_with_two_stops(
        db_session
    )

    token = get_token(db_client, user.email)

    response = db_client.post(
        "/api/v1/journeys/observations",
        headers=headers(token),
        json=observation_payload(route, first_stop, second_stop),
    )

    assert response.status_code == 403

    observations = db_session.scalars(
        select(JourneyObservation)
    ).all()

    assert observations == []


# ---------------------------------------------------------
# Observation data validation
# ---------------------------------------------------------

def test_observation_rejects_stop_not_on_route(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "researcher",
        "researcher@example.com",
        UserRole.FIELD_RESEARCHER.value,
    )

    route, first_stop, second_stop = create_route_with_two_stops(
        db_session
    )

    unrelated_stop = create_stop(
        db_session,
        "Unrelated Test Stop",
    )

    token = get_token(db_client, user.email)

    payload = observation_payload(
        route,
        first_stop,
        unrelated_stop,
    )

    response = db_client.post(
        "/api/v1/journeys/observations",
        headers=headers(token),
        json=payload,
    )

    assert response.status_code == 422
    assert "does not belong" in response.json()["detail"]


def test_observation_rejects_reversed_stop_sequence(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "researcher",
        "researcher@example.com",
        UserRole.FIELD_RESEARCHER.value,
    )

    route, first_stop, second_stop = create_route_with_two_stops(
        db_session
    )

    token = get_token(db_client, user.email)

    payload = observation_payload(
        route,
        second_stop,
        first_stop,
    )

    response = db_client.post(
        "/api/v1/journeys/observations",
        headers=headers(token),
        json=payload,
    )

    assert response.status_code == 422
    assert "must occur before" in response.json()["detail"]


def test_observation_rejects_inactive_route(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "researcher",
        "researcher@example.com",
        UserRole.FIELD_RESEARCHER.value,
    )

    route, first_stop, second_stop = create_route_with_two_stops(
        db_session
    )

    route.is_active = False
    db_session.commit()

    token = get_token(db_client, user.email)

    response = db_client.post(
        "/api/v1/journeys/observations",
        headers=headers(token),
        json=observation_payload(route, first_stop, second_stop),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Route not found or inactive."


def test_observation_rejects_invalid_duration(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "researcher",
        "researcher@example.com",
        UserRole.FIELD_RESEARCHER.value,
    )

    route, first_stop, second_stop = create_route_with_two_stops(
        db_session
    )

    token = get_token(db_client, user.email)

    payload = observation_payload(route, first_stop, second_stop)
    payload["duration_seconds"] = 0

    response = db_client.post(
        "/api/v1/journeys/observations",
        headers=headers(token),
        json=payload,
    )

    assert response.status_code == 422


def test_observation_is_persisted_as_unverified(
    db_client,
    db_session,
    clean_auth_tables,
    clean_transport_tables,
):
    user = create_user(
        db_session,
        "researcher",
        "researcher@example.com",
        UserRole.FIELD_RESEARCHER.value,
    )

    route, first_stop, second_stop = create_route_with_two_stops(
        db_session
    )

    token = get_token(db_client, user.email)

    response = db_client.post(
        "/api/v1/journeys/observations",
        headers=headers(token),
        json=observation_payload(route, first_stop, second_stop),
    )

    assert response.status_code == 201

    observation_id = response.json()["observation"]["id"]

    db_session.expire_all()

    saved = db_session.get(JourneyObservation, observation_id)

    assert saved is not None
    assert saved.is_verified is False
    assert saved.source == "field"
    assert saved.weekday == 1  # 17 November 2026 is Tuesday.
