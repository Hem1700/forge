"""Authentication helpers for WebSocket connections.

WebSocket handshakes can't easily carry an Authorization header, so the
token rides in the `?token=` query param. Accepts the same JWT or API key
that the REST endpoints take.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.api_key import ApiKey
from app.models.user import User


async def user_from_token(token: str, db: AsyncSession) -> User | None:
    """Resolve a token (JWT or API key) to a User, or None if invalid."""
    if not token:
        return None

    # Try JWT first
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id:
            user = (
                await db.execute(
                    select(User).where(User.id == user_id, User.is_active == True)  # noqa: E712
                )
            ).scalar_one_or_none()
            if user is not None:
                return user
    except JWTError:
        pass

    # Try API key
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    api_key = (
        await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if api_key is None:
        return None

    api_key.last_used_at = datetime.utcnow()
    user = (
        await db.execute(
            select(User).where(User.id == api_key.user_id, User.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    return user
