"""Org-admin routes: manage users within the organisation.

Accessible to users with `admin` or `super_admin` role.
All queries are scoped to the requesting user's org_id — admins cannot
see or modify users from other organisations.
Admins may not promote users to `super_admin` — that privilege is reserved
for super-admins only.
"""
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/org", tags=["org-admin"])


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    position: str | None = None


class UpdateRoleRequest(BaseModel):
    role: UserRole


class InviteRequest(BaseModel):
    role: UserRole = UserRole.viewer


class InviteResponse(BaseModel):
    token: str
    invite_url: str
    expires_in_days: int = 7


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    requesting_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """Return all active users in the requesting user's organisation."""
    result = await db.execute(
        select(User).where(
            User.org_id == requesting_user.org_id,
            User.is_active == True,  # noqa: E712
        )
    )
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: uuid.UUID,
    payload: UpdateRoleRequest,
    requesting_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update the role of a user within the same organisation."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == requesting_user.org_id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.role == UserRole.super_admin and requesting_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can promote to super_admin",
        )
    target.role = payload.role
    await db.commit()
    await db.refresh(target)
    return UserResponse.model_validate(target)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    requesting_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a user within the same organisation."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == requesting_user.org_id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == requesting_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target.is_active = False
    await db.commit()


@router.post("/invite", response_model=InviteResponse)
async def create_invite(
    payload: InviteRequest,
    requesting_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> InviteResponse:
    """Generate a signed invite token granting a specific role in this org."""
    if payload.role == UserRole.super_admin and requesting_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can invite with super_admin role",
        )

    org = (await db.execute(select(Organization).where(Organization.id == requesting_user.org_id))).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=400, detail="Your account has no organisation")

    expire = datetime.utcnow() + timedelta(days=7)
    token = jwt.encode(
        {
            "type": "invite",
            "org_id": str(org.id),
            "org_name": org.name,
            "role": payload.role.value,
            "exp": expire,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    invite_url = f"{settings.frontend_url}/login?invite={token}"
    return InviteResponse(token=token, invite_url=invite_url)
