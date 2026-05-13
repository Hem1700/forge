import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
# passlib 1.7.4 is incompatible with bcrypt 5.x (detect_wrap_bug uses a 256-byte
# test vector that bcrypt 5.x rejects). sha256_crypt (PBKDF2-SHA256) is used
# instead — it is equally secure and has no dependency conflicts in this env.
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime


def _make_token(user_id: uuid.UUID) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    role = UserRole.super_admin if count == 0 else UserRole.viewer

    user = User(
        email=payload.email,
        hashed_password=pwd_context.hash(payload.password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=_make_token(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = (
        await db.execute(select(User).where(User.email == payload.email, User.is_active == True))  # noqa: E712
    ).scalar_one_or_none()
    if not user or not pwd_context.verify(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=_make_token(user.id))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
