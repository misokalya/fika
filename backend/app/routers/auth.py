
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import User, UserRole
from app.schemas import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
)
from app.services.auth.security import (
    hash_password,
    verify_password,
)
from app.services.auth.tokens import create_access_token
from app.services.auth.dependencies import get_current_user
from app.services.auth.dependencies import require_roles


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserRegister,
    db: Session = Depends(get_db),
):
    """Register a new passenger account."""

    # Check for an existing username or email.
    existing_user = db.query(User).filter(
        or_(
            User.username == user_data.username,
            User.email == str(user_data.email).lower(),
        )
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered.",
        )

    new_user = User(
        username=user_data.username,
        email=str(user_data.email).lower(),
        password_hash=hash_password(user_data.password),
        role=UserRole.PASSENGER.value,
        is_active=True,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered.",
        )

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    login_data: UserLogin,
    db: Session = Depends(get_db),
):
    """Authenticate a user and return an access token."""

    email = str(login_data.email).lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    # Use a generic response to avoid revealing whether an account exists.
    if not user or not verify_password(
        login_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
    )

@router.get(
    "/me",
    response_model=UserResponse,
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """Return the authenticated user's profile."""

    return current_user

@router.get("/admin-check")
def admin_access_check(
    current_user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    return {
        "status": "success",
        "message": "Administrator access granted.",
        "user_id": current_user.id,
        "role": current_user.role,
    }