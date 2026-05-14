"""API Key management endpoints.

Allows authenticated users to create, list, and revoke their own API keys.
The raw key is returned only at creation time — afterwards only the prefix
(first 8 characters) is stored and exposed for identification.
"""

import hashlib
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


class CreateApiKeyRequest(BaseModel):
    name: str


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None


class CreateApiKeyResponse(ApiKeyResponse):
    """Extends ApiKeyResponse with the raw key, returned only at creation time."""

    key: str


@router.get("/", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyResponse]:
    """Return all active API keys belonging to the current user."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.is_active == True)  # noqa: E712
    )
    return [ApiKeyResponse.model_validate(k) for k in result.scalars().all()]


@router.post("/", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: CreateApiKeyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CreateApiKeyResponse:
    """Generate a new API key for the current user.

    The plaintext key is returned exactly once in this response. It is stored
    only as a SHA-256 hash — there is no way to recover the key later.
    """
    raw_key = secrets.token_urlsafe(32)
    api_key = ApiKey(
        user_id=user.id,
        name=payload.name,
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        prefix=raw_key[:8],
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return CreateApiKeyResponse(
        **ApiKeyResponse.model_validate(api_key).model_dump(),
        key=raw_key,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete (deactivate) an API key.

    Returns 404 if the key does not exist or belongs to a different user,
    preventing enumeration of other users' key IDs.
    """
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    api_key.is_active = False
    await db.commit()
