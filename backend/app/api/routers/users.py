from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import AppError
from app.models import EventLog, User
from app.models import PasswordResetToken
from app.schemas.auth import AdminPasswordResetRequest
from app.schemas.serializers import serialize_user
from app.security.dependencies import require_roles
from app.security.passwords import hash_password

router = APIRouter(prefix="/api", tags=["users"])
admin_user = require_roles("admin")


@router.get("/users")
def list_accounts(
    limit: int = 100,
    offset: int = 0,
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return safe profile fields to admins; credential hashes are never serialized."""
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    statement = select(User)
    if admin.source == "demo":
        statement = statement.where(User.source == "demo")
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    users = db.scalars(statement.order_by(User.created_at, User.id).offset(offset).limit(limit)).all()
    return {"items": [serialize_user(user) for user in users], "total": total, "limit": limit, "offset": offset}


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: str,
    body: AdminPasswordResetRequest,
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(admin)
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "user_not_found", "User was not found")
    user.password_hash = hash_password(body.password)
    user.auth_version += 1
    now = datetime.now(timezone.utc)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: now}, synchronize_session=False)
    db.add(EventLog(
        actor_user_id=admin.id,
        action="admin_password_reset",
        object_type="user",
        object_id=user.id,
        summary=f"Admin reset password for account {user.id}",
        details={"target_role": user.role},
        source="admin_api",
    ))
    db.commit()
    return {"message": "Password updated; existing sessions have been invalidated."}


@router.get("/users/pending")
def list_pending_users(
    _admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict[str, list[dict]]:
    # This legacy demo placeholder is not a real signup request. Exclude it even
    # before demo seeding has run against an older local database.
    statement = select(User).where(
        User.approval_status == "pending",
        User.id != "demo-pending-worker",
    )
    if _admin.source == "demo":
        statement = statement.where(User.source == "demo")
    users = db.scalars(statement.order_by(User.created_at, User.id)).all()
    return {"items": [serialize_user(user) for user in users]}


@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: str,
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(admin)
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "user_not_found", "User was not found")
    if user.approval_status != "pending":
        raise AppError(409, "approval_conflict", "Only pending accounts can be approved")

    user.role = "worker"  # Publicly registered accounts can never become administrators.
    user.approval_status = "approved"
    user.is_active = True
    user.worker_id = user.worker_id or f"WKR-{uuid4().hex[:12].upper()}"
    db.add(EventLog(
        actor_user_id=admin.id,
        action="account_approved",
        object_type="user",
        object_id=user.id,
        summary=f"Approved worker account {user.email}",
        details={"approval_status": "approved", "role": "worker", "worker_id": user.worker_id},
        source="auth",
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "approval_conflict", "The account could not be approved") from exc
    db.refresh(user)
    return serialize_user(user)


@router.post("/users/{user_id}/reject")
def reject_user(
    user_id: str,
    admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> dict:
    _reject_demo_write(admin)
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "user_not_found", "User was not found")
    if user.approval_status != "pending":
        raise AppError(409, "approval_conflict", "Only pending accounts can be rejected")

    user.approval_status = "rejected"
    user.is_active = False
    db.add(EventLog(
        actor_user_id=admin.id,
        action="account_rejected",
        object_type="user",
        object_id=user.id,
        summary=f"Rejected access request {user.email}",
        details={"approval_status": "rejected"},
        source="auth",
    ))
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.get("/workers")
def list_workers(
    _admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> dict[str, list[dict]]:
    statement = select(User).where(User.role == "worker", User.approval_status == "approved", User.is_active.is_(True))
    if _admin.source == "demo":
        statement = statement.where(User.source == "demo")
    workers = db.scalars(statement.order_by(User.name, User.id)).all()
    return {
        "items": [
            {
                "id": user.id,
                "worker_id": user.worker_id,
                "name": user.name,
                "email": user.email,
                "city": user.city,
                "status": "ACTIVE",
            }
            for user in workers
        ]
    }


def _reject_demo_write(user: User) -> None:
    if user.source == "demo":
        raise AppError(403, "demo_read_only", "Demo data is read-only. No changes were saved.")
