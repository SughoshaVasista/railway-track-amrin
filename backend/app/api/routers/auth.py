import hashlib
import logging
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import AppError
from app.models import EventLog, PasswordResetToken, User
from app.schemas.auth import ForgotPasswordRequest, LoginRequest, LoginResponse, PublicUser, RegisterRequest, RegistrationResponse, ResetPasswordRequest
from app.schemas.serializers import serialize_user
from app.security.dependencies import get_current_user
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger("amrin.auth")


def _create_access_token(request: Request, user: User) -> str:
    secret = request.app.state.settings.jwt_secret_key
    if not secret:
        raise AppError(503, "auth_unconfigured", "Authentication is not configured")
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=request.app.state.settings.jwt_access_token_minutes)
    return jwt.encode(
        {"sub": user.id, "iat": now, "exp": expires, "jti": uuid4().hex, "ver": user.auth_version, "type": "access"},
        secret,
        algorithm="HS256",
    )


def _send_password_reset(request: Request, email: str, token: str) -> None:
    settings = request.app.state.settings
    link = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={token}"
    if not all((settings.smtp_host, settings.smtp_from)):
        if settings.environment.lower() not in {"production", "prod"}:
            logger.info("Development password reset link for %s: %s", email, link)
        else:
            logger.error("Password reset delivery is not configured")
        return
    message = EmailMessage()
    message["Subject"] = "RailSafe password reset"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"Use this link to reset your RailSafe password. It expires in 30 minutes:\n\n{link}\n\nIf you did not request this, ignore this email.")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    email = str(payload.email).strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active.is_(True)))
    if user is not None and user.password_hash:
        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({PasswordResetToken.used_at: now}, synchronize_session=False)
        reset_record = PasswordResetToken(
            id=uuid4().hex,
            user_id=user.id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=now + timedelta(minutes=30),
        )
        db.add(reset_record)
        db.commit()
        try:
            _send_password_reset(request, user.email, raw_token)
        except (OSError, smtplib.SMTPException):
            logger.exception("Password reset delivery failed")
            db.delete(reset_record)
            db.commit()
    return {"message": "If an active account matches that email, password reset instructions will be sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    now = datetime.now(timezone.utc)
    if reset is None or reset.used_at is not None or reset.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise AppError(400, "invalid_reset_token", "The password reset link is invalid or expired")
    user = db.get(User, reset.user_id)
    if user is None or not user.is_active:
        raise AppError(400, "invalid_reset_token", "The password reset link is invalid or expired")
    user.password_hash = hash_password(payload.password)
    user.auth_version += 1
    reset.used_at = now
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.id != reset.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: now}, synchronize_session=False)
    db.add(EventLog(actor_user_id=user.id, action="password_reset", object_type="user", object_id=user.id,
                    summary="Account password reset", details={}, source="auth"))
    db.commit()
    return {"message": "Password updated. Sign in with the new password."}


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    identifier = payload.username.strip().lower()
    if request.app.state.settings.demo_mode and identifier in {"admin", "demo-admin"} and payload.password == "admin":
        demo_admin = db.get(User, "demo-admin")
        if demo_admin is not None and demo_admin.is_active and demo_admin.approval_status == "approved":
            return {"token": _create_access_token(request, demo_admin), "role": "admin", "name": demo_admin.name, "worker_id": None, "city": None, "source": demo_admin.source}
    if request.app.state.settings.demo_mode and identifier in {"worker", "worker-01"} and payload.password == "worker":
        demo_worker = db.get(User, "worker-01")
        if demo_worker is not None and demo_worker.is_active and demo_worker.approval_status == "approved":
            return {"token": _create_access_token(request, demo_worker), "role": "worker", "name": demo_worker.name, "worker_id": demo_worker.worker_id, "city": demo_worker.city, "source": demo_worker.source}
    user = db.scalar(
        select(User).where(or_(func.lower(User.email) == identifier, func.lower(User.username) == identifier))
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Email/username or password is incorrect")
    if user.approval_status == "pending":
        raise AppError(403, "pending_approval", "This account is awaiting administrator approval")
    if user.approval_status != "approved" or not user.is_active:
        raise AppError(401, "invalid_credentials", "Email/username or password is incorrect")

    return {
        "token": _create_access_token(request, user),
        "role": user.role,
        "name": user.name,
        "worker_id": user.worker_id,
        "city": user.city,
        "source": user.source,
    }


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = str(payload.email).strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise AppError(409, "email_exists", "An account with this email already exists")

    # Public role requests are never trusted. Operator/admin requests become a pending worker account.
    user = User(
        id=f"USER-{uuid4().hex}",
        name=payload.name,
        email=email,
        username=None,
        password_hash=hash_password(payload.password),
        role="worker",
        approval_status="pending",
        city=payload.city,
        worker_id=None,
        is_active=True,
        source="registration",
    )
    db.add(user)
    db.add(EventLog(
        actor_user_id=None,
        action="account_registration_requested",
        object_type="user",
        object_id=user.id,
        summary="A new account requested access",
        details={"requested_role": payload.role, "assigned_role": "worker"},
        source="auth",
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "email_exists", "An account with this email already exists") from exc
    db.refresh(user)
    return {"message": "Account created and is awaiting administrator approval", "user": serialize_user(user)}


@router.get("/me", response_model=PublicUser)
def me(user: User = Depends(get_current_user)) -> dict:
    return serialize_user(user)
