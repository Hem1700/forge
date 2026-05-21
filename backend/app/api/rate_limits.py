# backend/app/api/rate_limits.py
"""Per-org rate limit configuration endpoints."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.brain.llm_factory import Provider, _DEFAULT_RATE_LIMITS, _get_rl_redis
from app.database import get_db
from app.models.org_rate_limit import OrgRateLimitConfig
from app.models.user import User

router = APIRouter(prefix="/api/v1/org/rate-limits", tags=["rate-limits"])


class RateLimitSetRequest(BaseModel):
    provider: str
    tpm_limit: int | None = None
    rpm_limit: int | None = None


@router.get("")
async def get_rate_limits(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if current_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    rows = (await db.execute(
        select(OrgRateLimitConfig).where(OrgRateLimitConfig.org_id == current_user.org_id)
    )).scalars().all()
    overrides = {r.provider: r for r in rows}

    result = {}
    for prov, defaults in _DEFAULT_RATE_LIMITS.items():
        row = overrides.get(prov)
        result[prov] = {
            "tpm_limit": row.tpm_limit if row and row.tpm_limit is not None else defaults["tpm"],
            "rpm_limit": row.rpm_limit if row and row.rpm_limit is not None else defaults["rpm"],
            "custom": row is not None,
        }
    # Show live window usage from Redis
    try:
        import time as _t
        redis = await _get_rl_redis()
        now_ms = int(_t.time() * 1000)
        org_str = str(current_user.org_id)
        for prov in result:
            for window in ("tpm", "rpm"):
                key = f"ratelimit:{org_str}:{prov}:{window}"
                await redis.zremrangebyscore(key, "-inf", now_ms - 60_000)
                count = await redis.zcard(key)
                result[prov][f"{window}_used"] = count
    except Exception:
        pass
    return result


@router.put("")
async def set_rate_limit(
    body: RateLimitSetRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if current_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    try:
        Provider(body.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {body.provider}")

    row = (await db.execute(
        select(OrgRateLimitConfig).where(
            OrgRateLimitConfig.org_id == current_user.org_id,
            OrgRateLimitConfig.provider == body.provider,
        )
    )).scalar_one_or_none()
    if row is None:
        row = OrgRateLimitConfig(
            org_id=current_user.org_id,
            provider=body.provider,
            tpm_limit=body.tpm_limit,
            rpm_limit=body.rpm_limit,
        )
        db.add(row)
    else:
        row.tpm_limit = body.tpm_limit
        row.rpm_limit = body.rpm_limit
    await db.commit()
    return {"ok": True, "provider": body.provider}


@router.delete("")
async def reset_rate_limits(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if current_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    await db.execute(
        sa_delete(OrgRateLimitConfig).where(OrgRateLimitConfig.org_id == current_user.org_id)
    )
    await db.commit()
    return {"ok": True, "reset_to_defaults": True}
