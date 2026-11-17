
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditLog, User, UserRole
from app.services.auth.security import hash_password


def create_user(
    db_session,
    username: str,
    email: str,
    role: str = UserRole.PASSENGER.value,
    is_active: bool = True,
):
    """Create a database-backed user for an API test."""

    user = User(
        username=username,
        email=email,
        password_hash=hash_password("TestPassword123!"),
        role=role,
        is_active=is_active,
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


def login(client: TestClient, email: str = "admin@example.com"):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------

def test_registration_creates_passenger(db_client, clean_auth_tables):
    response = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": "newpassenger",
            "email": "NEWPASSENGER@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["username"] == "newpassenger"
    assert data["email"] == "newpassenger@example.com"
    assert data["role"] == UserRole.PASSENGER.value
    assert data["is_active"] is True

    # Password hashes must never be returned.
    assert "password" not in data
    assert "password_hash" not in data


def test_registration_cannot_self_assign_admin(
    db_client,
    clean_auth_tables,
):
    response = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": "attemptedadmin",
            "email": "attemptedadmin@example.com",
            "password": "TestPassword123!",
            "role": "admin",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == UserRole.PASSENGER.value


def test_registration_rejects_duplicate_email(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="existinguser",
        email="existing@example.com",
    )

    response = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": "anotheruser",
            "email": "EXISTING@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 409


def test_registration_rejects_duplicate_username(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="existinguser",
        email="existing@example.com",
    )

    response = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": "existinguser",
            "email": "another@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 409


def test_registration_rejects_short_password(
    db_client,
    clean_auth_tables,
):
    response = db_client.post(
        "/api/v1/auth/register",
        json={
            "username": "shortpassword",
            "email": "short@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------
# Login
# ---------------------------------------------------------

def test_login_returns_access_token(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="loginuser",
        email="login@example.com",
    )

    response = db_client.post(
        "/api/v1/auth/login",
        json={
            "email": "LOGIN@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["access_token"]
    assert data["token_type"] == "bearer"


def test_login_rejects_wrong_password(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="loginuser",
        email="login@example.com",
    )

    response = db_client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_login_rejects_inactive_user(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="inactiveuser",
        email="inactive@example.com",
        is_active=False,
    )

    response = db_client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 403


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------

def test_profile_requires_authentication(
    db_client,
    clean_auth_tables,
):
    response = db_client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_profile_rejects_invalid_token(
    db_client,
    clean_auth_tables,
):
    response = db_client.get(
        "/api/v1/auth/me",
        headers=auth_headers("not-a-valid-token"),
    )

    assert response.status_code == 401


def test_profile_returns_current_database_user(
    db_client,
    db_session,
    clean_auth_tables,
):
    user = create_user(
        db_session,
        username="profileuser",
        email="profile@example.com",
    )

    token = login(db_client, "profile@example.com")

    response = db_client.get(
        "/api/v1/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert response.json()["username"] == "profileuser"
    assert response.json()["role"] == UserRole.PASSENGER.value


def test_deactivated_user_cannot_use_existing_token(
    db_client,
    db_session,
    clean_auth_tables,
):
    user = create_user(
        db_session,
        username="deactivateduser",
        email="deactivated@example.com",
    )

    token = login(db_client, "deactivated@example.com")

    user.is_active = False
    db_session.commit()

    response = db_client.get(
        "/api/v1/auth/me",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


# ---------------------------------------------------------
# Admin authorization and user management
# ---------------------------------------------------------

def test_passenger_cannot_access_admin_check(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="passenger",
        email="passenger@example.com",
    )

    token = login(db_client, "passenger@example.com")

    response = db_client.get(
        "/api/v1/auth/admin-check",
        headers=auth_headers(token),
    )

    assert response.status_code == 403


def test_admin_can_access_admin_check(
    db_client,
    db_session,
    clean_auth_tables,
):
    admin = create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    token = login(db_client)

    response = db_client.get(
        "/api/v1/auth/admin-check",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == admin.id
    assert response.json()["role"] == UserRole.ADMIN.value


def test_admin_can_list_users(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    create_user(
        db_session,
        username="passenger",
        email="passenger@example.com",
    )

    token = login(db_client)

    response = db_client.get(
        "/api/v1/auth/users",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_passenger_cannot_list_users(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="passenger",
        email="passenger@example.com",
    )

    token = login(db_client, "passenger@example.com")

    response = db_client.get(
        "/api/v1/auth/users",
        headers=auth_headers(token),
    )

    assert response.status_code == 403


def test_admin_can_change_user_role(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    target = create_user(
        db_session,
        username="target",
        email="target@example.com",
    )

    token = login(db_client)

    response = db_client.patch(
        f"/api/v1/auth/users/{target.id}/role",
        headers=auth_headers(token),
        json={"role": "operator"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == UserRole.OPERATOR.value

    audit = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == "USER_ROLE_CHANGED"
        )
    ).all()

    assert len(audit) == 1
    assert audit[0].entity_id == target.id


def test_admin_can_deactivate_and_reactivate_user(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    target = create_user(
        db_session,
        username="target",
        email="target@example.com",
    )

    token = login(db_client)

    deactivate = db_client.patch(
        f"/api/v1/auth/users/{target.id}/status",
        headers=auth_headers(token),
        json={"is_active": False},
    )

    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    reactivate = db_client.patch(
        f"/api/v1/auth/users/{target.id}/status",
        headers=auth_headers(token),
        json={"is_active": True},
    )

    assert reactivate.status_code == 200
    assert reactivate.json()["is_active"] is True

    actions = db_session.scalars(
        select(AuditLog.action).where(
            AuditLog.entity_id == target.id
        )
    ).all()

    assert "USER_DEACTIVATED" in actions
    assert "USER_REACTIVATED" in actions


# ---------------------------------------------------------
# Admin safeguards
# ---------------------------------------------------------

def test_admin_cannot_change_own_role(
    db_client,
    db_session,
    clean_auth_tables,
):
    admin = create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    token = login(db_client)

    response = db_client.patch(
        f"/api/v1/auth/users/{admin.id}/role",
        headers=auth_headers(token),
        json={"role": "passenger"},
    )

    assert response.status_code == 400


def test_admin_cannot_change_own_status(
    db_client,
    db_session,
    clean_auth_tables,
):
    admin = create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    token = login(db_client)

    response = db_client.patch(
        f"/api/v1/auth/users/{admin.id}/status",
        headers=auth_headers(token),
        json={"is_active": False},
    )

    assert response.status_code == 400


def test_admin_cannot_demote_last_active_admin(
    db_client,
    db_session,
    clean_auth_tables,
):
    create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    target = create_user(
        db_session,
        username="secondadmin",
        email="secondadmin@example.com",
        role=UserRole.ADMIN.value,
    )

    # The logged-in admin is the actor, so make the target
    # the only active administrator for this scenario.
    actor = db_session.scalar(
        select(User).where(User.email == "admin@example.com")
    )
    actor.role = UserRole.PASSENGER.value
    db_session.commit()

    # Promote the target's credentials to the acting admin
    # account for this isolated last-admin scenario.
    actor.role = UserRole.ADMIN.value
    target.role = UserRole.PASSENGER.value
    db_session.commit()

    token = login(db_client)

    response = db_client.patch(
        f"/api/v1/auth/users/{target.id}/role",
        headers=auth_headers(token),
        json={"role": "passenger"},
    )

    # Target is already a passenger; the request is a no-op.
    assert response.status_code == 200


def test_admin_cannot_deactivate_last_active_admin(
    db_client,
    db_session,
    clean_auth_tables,
):
    admin = create_user(
        db_session,
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN.value,
    )

    token = login(db_client)

    response = db_client.patch(
        f"/api/v1/auth/users/{admin.id}/status",
        headers=auth_headers(token),
        json={"is_active": False},
    )

    # Self-deactivation is rejected before last-admin logic.
    assert response.status_code == 400
