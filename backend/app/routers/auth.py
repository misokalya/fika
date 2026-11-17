
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import User, UserRole, AuditLog
from app.schemas import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.services.auth.security import (
    hash_password,
    verify_password,
)
from app.services.auth.tokens import create_access_token
from app.services.auth.dependencies import (
    get_current_user,
    require_roles,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


admin_only = require_roles(UserRole.ADMIN)


def count_active_admins(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(
            User.role == UserRole.ADMIN.value,
            User.is_active.is_(True),
        )
    ) or 0


def record_audit(
    db: Session,
    actor: User,
    action: str,
    target: User,
    details: dict,
):
    db.add(
        AuditLog(
            actor=f"{actor.username} (ID: {actor.id})",
            action=action,
            entity_type="User",
            entity_id=target.id,
            details=details,
        )
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
    return current_user


@router.get("/admin-check")
def admin_access_check(
    current_user: User = Depends(admin_only),
):
    return {
        "status": "success",
        "message": "Administrator access granted.",
        "user_id": current_user.id,
        "role": current_user.role,
    }


@router.get(
    "/users",
    response_model=list[UserResponse],
)
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """List registered users. Administrator only."""

    if skip < 0:
        raise HTTPException(
            status_code=400,
            detail="skip cannot be negative.",
        )

    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 500.",
        )

    query = (
        select(User)
        .order_by(User.id)
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(query).all()


@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse,
)
def update_user_role(
    user_id: int,
    request: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Change a user's role. Administrator only."""

    target = db.get(User, user_id)

    if target is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    if target.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own administrator role.",
        )

    old_role = target.role
    new_role = request.role

    if old_role == new_role:
        return target

    if (
        old_role == UserRole.ADMIN.value
        and target.is_active
        and new_role != UserRole.ADMIN.value
        and count_active_admins(db) <= 1
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the last active administrator.",
        )

    target.role = new_role

    record_audit(
        db=db,
        actor=current_user,
        action="USER_ROLE_CHANGED",
        target=target,
        details={
            "old_role": old_role,
            "new_role": new_role,
        },
    )

    try:
        db.commit()
        db.refresh(target)
    except Exception:
        db.rollback()
        raise

    return target


@router.patch(
    "/users/{user_id}/status",
    response_model=UserResponse,
)
def update_user_status(
    user_id: int,
    request: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Activate or deactivate a user. Administrator only."""

    target = db.get(User, user_id)

    if target is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    if target.id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own account status.",
        )

    old_status = target.is_active
    new_status = request.is_active

    if old_status == new_status:
        return target

    if (
        target.role == UserRole.ADMIN.value
        and old_status
        and not new_status
        and count_active_admins(db) <= 1
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate the last active administrator.",
        )

    target.is_active = new_status

    action = (
        "USER_REACTIVATED"
        if new_status
        else "USER_DEACTIVATED"
    )

    record_audit(
        db=db,
        actor=current_user,
        action=action,
        target=target,
        details={
            "old_is_active": old_status,
            "new_is_active": new_status,
        },
    )

    try:
        db.commit()
        db.refresh(target)
    except Exception:
        db.rollback()
        raise

    return target
