import uuid
from datetime import datetime, timedelta

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole

_redis_client: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = await aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def _check_rate_limit(request: Request, action: str) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"rl:{action}:{ip}"
    try:
        r = await _get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)
        if count > 10:
            ttl = await r.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again later.",
                headers={"Retry-After": str(max(ttl, 1))},
            )
    except HTTPException:
        raise
    except Exception:
        pass

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
# passlib 1.7.4 is incompatible with bcrypt 5.x (detect_wrap_bug uses a 256-byte
# test vector that bcrypt 5.x rejects). sha256_crypt (PBKDF2-SHA256) is used
# instead — it is equally secure and has no dependency conflicts in this env.
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: str
    password: str
    org_name: str = ""
    position: str | None = None
    invite_token: str | None = None


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
    org_id: uuid.UUID | None = None
    org_name: str | None = None
    position: str | None = None
    is_platform_admin: bool = False


def _make_token(user_id: uuid.UUID) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    await _check_rate_limit(request, "login")
    existing = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # -- Invite token path --
    if payload.invite_token:
        try:
            claims = jwt.decode(payload.invite_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        except JWTError:
            raise HTTPException(status_code=400, detail="Invalid or expired invite link")
        if claims.get("type") != "invite":
            raise HTTPException(status_code=400, detail="Invalid invite token")

        org_id = uuid.UUID(claims["org_id"])
        org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=400, detail="Organisation no longer exists")

        role = UserRole(claims["role"])
        user = User(
            email=payload.email,
            hashed_password=pwd_context.hash(payload.password),
            role=role,
            org_id=org.id,
            position=payload.position,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return TokenResponse(access_token=_make_token(user.id))

    # -- Normal registration path --
    org_name = payload.org_name.strip()
    if not org_name:
        raise HTTPException(status_code=400, detail="org_name is required when not using an invite link")

    existing_org = (
        await db.execute(select(Organization).where(func.lower(Organization.name) == org_name.lower()))
    ).scalar_one_or_none()
    if existing_org is not None:
        raise HTTPException(status_code=400, detail="Organisation name already taken — ask an admin for an invite link")

    org = Organization(name=org_name)
    db.add(org)
    await db.flush()
    role = UserRole.super_admin

    user = User(
        email=payload.email,
        hashed_password=pwd_context.hash(payload.password),
        role=role,
        org_id=org.id,
        position=payload.position,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=_make_token(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    await _check_rate_limit(request, "login")
    user = (
        await db.execute(select(User).where(User.email == payload.email, User.is_active == True))  # noqa: E712
    ).scalar_one_or_none()
    if not user or not pwd_context.verify(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=_make_token(user.id))


class FCMTokenRequest(BaseModel):
    token: str


@router.post("/fcm-token", status_code=status.HTTP_200_OK)
async def register_fcm_token(
    body: FCMTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_user.fcm_token = body.token
    await db.commit()
    return {"status": "ok"}


async def _serialize_user(user: User, db: AsyncSession) -> UserResponse:
    org_name: str | None = None
    if user.org_id:
        org = (await db.execute(select(Organization).where(Organization.id == user.org_id))).scalar_one_or_none()
        org_name = org.name if org else None
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        org_id=user.org_id,
        org_name=org_name,
        position=user.position,
        is_platform_admin=user.is_platform_admin,
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> UserResponse:
    return await _serialize_user(user, db)


class UpdateMeRequest(BaseModel):
    email: str | None = None
    position: str | None = None


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    if body.email is not None and body.email != current_user.email:
        taken = (
            await db.execute(select(User).where(User.email == body.email))
        ).scalar_one_or_none()
        if taken:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = body.email
    if body.position is not None:
        current_user.position = body.position
    await db.commit()
    await db.refresh(current_user)
    return await _serialize_user(current_user, db)
