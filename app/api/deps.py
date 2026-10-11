"""Shared API dependencies: auth, current user, RBAC guards."""
from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.crud import user as crud_user
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=True,
)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise CREDENTIALS_EXCEPTION from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise CREDENTIALS_EXCEPTION

    subject = payload.get("sub")
    if subject is None:
        raise CREDENTIALS_EXCEPTION

    try:
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError) as exc:
        raise CREDENTIALS_EXCEPTION from exc

    user = await crud_user.get_user(db, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user account"
        )
    return current_user


class RoleChecker:
    """Dependency factory that allows only the listed roles."""

    def __init__(self, *roles: UserRole) -> None:
        self.allowed_roles = set(roles)

    def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Insufficient permissions. Required role(s): "
                    + ", ".join(sorted(r.value for r in self.allowed_roles))
                ),
            )
        return user


require_customer = RoleChecker(UserRole.CUSTOMER)
require_vendor = RoleChecker(UserRole.VENDOR)
require_rider = RoleChecker(UserRole.RIDER)


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    return RoleChecker(*roles)
