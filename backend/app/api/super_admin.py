"""Super-admin routes: platform-level user management.

All endpoints require the `super_admin` role.  Unlike org-admin routes,
these operate across ALL users (including inactive ones) and can promote
users to any role including `super_admin`.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_super_admin
from app.database import get_db
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/admin", tags=["super-admin"])
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    is_active: bool


class UpdateRoleRequest(BaseModel):
    role: UserRole


class ProvisionRequest(BaseModel):
    email: str
    password: str
    role: UserRole = UserRole.viewer


@router.get("/users", response_model=list[UserResponse])
async def list_all_users(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """Return ALL users, including inactive ones."""
    result = await db.execute(select(User))
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def set_user_role(
    user_id: uuid.UUID,
    payload: UpdateRoleRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Set the role of any user, including promoting to super_admin."""
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = payload.role
    await db.commit()
    await db.refresh(target)
    return UserResponse.model_validate(target)


@router.post("/provision", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def provision_user(
    payload: ProvisionRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user with a specified role.

    Useful for on-boarding team members without requiring them to self-register.
    Returns 400 if the email is already taken.
    """
    existing = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email,
        hashed_password=pwd_context.hash(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)
