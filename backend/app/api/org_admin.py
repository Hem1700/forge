"""Org-admin routes: manage users within the organisation.

Accessible to users with `admin` or `super_admin` role.
All queries are scoped to the requesting user's org_id — admins cannot
see or modify users from other organisations.
Admins may not promote users to `super_admin` — that privilege is reserved
for super-admins only.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.database import get_db
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
