
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import AuditLog, UserRole
from app.schemas import AuditLogResponse
from app.services.auth.dependencies import require_roles

router = APIRouter(
    prefix="/api/v1/admin/audit-logs",
    tags=["Admin - Audit Logs"],
)

admin_only = require_roles(UserRole.ADMIN)

@router.get(
    "",
    response_model=list[AuditLogResponse],
)
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    current_user=Depends(admin_only),
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    actor: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
):
    query = select(AuditLog)

    if actor:
        query = query.where(AuditLog.actor.ilike(f"%{actor}%"))

    if action:
        query = query.where(AuditLog.action == action)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)

    query = (
        query
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(query).all()