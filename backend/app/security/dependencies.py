from typing import Any, Callable

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import AppError
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_token_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(401, "missing_token", "A Bearer token is required")
    secret = request.app.state.settings.jwt_secret_key
    if not secret:
        raise AppError(503, "auth_unconfigured", "Authentication is not configured")
    try:
        claims = jwt.decode(credentials.credentials, secret, algorithms=["HS256"])
        if (
            claims.get("type") != "access"
            or not isinstance(claims.get("sub"), str)
            or not claims["sub"]
        ):
            raise AppError(401, "invalid_token", "The access token is invalid or expired")
        return claims
    except jwt.PyJWTError as exc:
        raise AppError(401, "invalid_token", "The access token is invalid or expired") from exc


def get_current_user(
    claims: dict[str, Any] = Depends(get_token_claims),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(select(User).where(User.id == claims["sub"]))
    if (
        user is None
        or not user.is_active
        or claims.get("ver", 0) != user.auth_version
        or user.approval_status != "approved"
        or user.role not in {"admin", "worker"}
    ):
        raise AppError(401, "invalid_account", "This account is not active")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def role_dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "forbidden", "You do not have permission to perform this action")
        return user

    return role_dependency
