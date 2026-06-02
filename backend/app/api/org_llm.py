# backend/app/api/org_llm.py
"""REST API for per-org LLM provider configuration."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.brain.llm_factory import (
    DEFAULT_TASK_SPECS, Provider, TaskType, _decrypt_key, _encrypt_key,
)
from app.database import get_db
from app.models.org_llm import OrgLLMAuditLog, OrgLLMCredential, OrgLLMTaskConfig
from app.models.llm_usage import LLMUsageEvent
from app.models.user import User

router = APIRouter(prefix="/api/v1/org/llm", tags=["org-llm"])

# ── Provider metadata ─────────────────────────────────────────────────────────

_PROVIDER_META = {
    Provider.anthropic: {
        "required_fields": ["api_key"],
        "optional_fields": [],
        "description": "Anthropic (Claude models)",
    },
    Provider.openai: {
        "required_fields": ["api_key"],
        "optional_fields": [],
        "description": "OpenAI (GPT models)",
    },
    Provider.bedrock: {
        "required_fields": [],
        "optional_fields": ["api_key", "region", "use_iam_role"],
        "description": "AWS Bedrock — use IAM role (recommended) or static keys",
    },
    Provider.azure: {
        "required_fields": ["api_key", "endpoint"],
        "optional_fields": [],
        "description": "Azure OpenAI — requires endpoint URL and API key",
    },
}

_SMART_MODELS = {
    Provider.anthropic: "claude-sonnet-4-6",
    Provider.openai: "gpt-4-turbo",
    Provider.bedrock: "anthropic.claude-sonnet-4",
    Provider.azure: "gpt-4-turbo",
}

_CHEAP_MODELS = {
    Provider.anthropic: "claude-haiku-4-5",
    Provider.openai: "gpt-4o-mini",
    Provider.bedrock: "anthropic.claude-haiku-4",
    Provider.azure: "gpt-4o-mini",
}


# ── Request / Response schemas ────────────────────────────────────────────────

class CredentialUpsertRequest(BaseModel):
    api_key: str | None = None
    region: str | None = None
    endpoint: str | None = None
    use_iam_role: bool = False


class TaskConfigEntry(BaseModel):
    provider: str
    model: str
    max_tokens: int | None = None
    temperature: float | None = None


class TaskConfigBulkRequest(BaseModel):
    preset: str | None = None  # "smart" | "balanced" | "cheap"
    custom: dict[str, TaskConfigEntry] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    payload: dict,
) -> None:
    log = OrgLLMAuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        payload=payload,
    )
    db.add(log)
    await db.flush()


def _cred_status(row: OrgLLMCredential) -> dict:
    return {
        "provider": row.provider,
        "configured": True,
        "use_iam_role": (row.extra or {}).get("use_iam_role", False),
        "region": row.region,
        "endpoint": row.endpoint,
        "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers(
    _: User = Depends(get_current_user),
) -> list[dict]:
    """Return supported providers and their required fields."""
    return [
        {"provider": p.value, **meta}
        for p, meta in _PROVIDER_META.items()
    ]


@router.get("/credentials")
async def list_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List configured providers for the caller's org. Never returns keys."""
    rows = (
        await db.execute(
            select(OrgLLMCredential).where(
                OrgLLMCredential.org_id == current_user.org_id
            )
        )
    ).scalars().all()
    configured = {row.provider: _cred_status(row) for row in rows}

    result = []
    for p in Provider:
        if p.value in configured:
            result.append(configured[p.value])
        else:
            result.append({"provider": p.value, "configured": False})
    return result


@router.put("/credentials/{provider}", status_code=200)
async def upsert_credentials(
    provider: str,
    body: CredentialUpsertRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or update credentials for a provider. Keys are Fernet-encrypted at rest."""
    try:
        prov = Provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    encrypted = _encrypt_key(body.api_key) if body.api_key else None

    row = (
        await db.execute(
            select(OrgLLMCredential).where(
                OrgLLMCredential.org_id == current_user.org_id,
                OrgLLMCredential.provider == prov.value,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = OrgLLMCredential(
            org_id=current_user.org_id,
            provider=prov.value,
        )
        db.add(row)

    if encrypted is not None:
        row.encrypted_key = encrypted
    row.region = body.region
    row.endpoint = body.endpoint
    row.extra = {"use_iam_role": body.use_iam_role}
    row.updated_at = datetime.utcnow()

    await _audit(
        db, current_user.org_id, current_user.id,
        "set_key",
        {"provider": prov.value, "use_iam_role": body.use_iam_role, "has_key": bool(body.api_key)},
    )
    await db.commit()
    await db.refresh(row)
    return _cred_status(row)


@router.post("/credentials/{provider}/test")
async def test_credentials(
    provider: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a minimal 1-token probe to validate the credentials."""
    try:
        prov = Provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    from app.brain.llm_factory import _build_anthropic, _build_openai, _build_azure, _build_bedrock, _resolve_credentials, LLMSpec
    from langchain_core.messages import HumanMessage

    try:
        spec = LLMSpec(provider=prov, model=_SMART_MODELS[prov], max_tokens=1)
        creds = await _resolve_credentials(prov, current_user.org_id)
        builders = {
            Provider.anthropic: _build_anthropic,
            Provider.openai: _build_openai,
            Provider.bedrock: _build_bedrock,
            Provider.azure: _build_azure,
        }
        llm = builders[prov](spec, creds)
        await llm.ainvoke([HumanMessage(content="hi")])

        row = (
            await db.execute(
                select(OrgLLMCredential).where(
                    OrgLLMCredential.org_id == current_user.org_id,
                    OrgLLMCredential.provider == prov.value,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.last_tested_at = datetime.utcnow()
        await _audit(db, current_user.org_id, current_user.id, "test", {"provider": prov.value, "ok": True})
        await db.commit()
        return {"ok": True}
    except Exception as exc:
        await _audit(db, current_user.org_id, current_user.id, "test", {"provider": prov.value, "ok": False, "error": str(exc)[:200]})
        await db.commit()
        return {"ok": False, "error": str(exc)[:500]}


@router.delete("/credentials/{provider}", status_code=200)
async def revoke_credentials(
    provider: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke (delete) stored credentials for a provider."""
    try:
        prov = Provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    row = (
        await db.execute(
            select(OrgLLMCredential).where(
                OrgLLMCredential.org_id == current_user.org_id,
                OrgLLMCredential.provider == prov.value,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No credentials found for this provider")

    await db.delete(row)
    await _audit(db, current_user.org_id, current_user.id, "revoke", {"provider": prov.value})
    await db.commit()
    return {"provider": prov.value, "revoked": True}


@router.get("/task-config")
async def get_task_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the full task → model map. Defaults shown for unconfigured rows."""
    rows = (
        await db.execute(
            select(OrgLLMTaskConfig).where(
                OrgLLMTaskConfig.org_id == current_user.org_id
            )
        )
    ).scalars().all()
    overrides = {row.task_type: row for row in rows}

    tasks: dict[str, Any] = {}
    for task in TaskType:
        default = DEFAULT_TASK_SPECS[task]
        if task.value in overrides:
            row = overrides[task.value]
            tasks[task.value] = {
                "provider": row.provider,
                "model": row.model,
                "max_tokens": row.max_tokens or default.max_tokens,
                "temperature": row.temperature if row.temperature is not None else default.temperature,
                "from_default": False,
            }
        else:
            tasks[task.value] = {
                "provider": default.provider.value,
                "model": default.model,
                "max_tokens": default.max_tokens,
                "temperature": default.temperature,
                "from_default": True,
            }

    # Detect preset
    preset = "custom"
    if not overrides:
        preset = "balanced"

    return {"preset": preset, "tasks": tasks}


@router.put("/task-config", status_code=200)
async def set_task_config(
    body: TaskConfigBulkRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bulk-set task config. Supply either preset or custom dict."""
    if body.preset and body.custom:
        raise HTTPException(status_code=400, detail="Supply either 'preset' or 'custom', not both")
    if not body.preset and not body.custom:
        raise HTTPException(status_code=400, detail="Supply either 'preset' or 'custom'")

    # Determine provider (default to anthropic if org has no cred configured)
    provider_row = (
        await db.execute(
            select(OrgLLMCredential).where(
                OrgLLMCredential.org_id == current_user.org_id
            ).limit(1)
        )
    ).scalar_one_or_none()
    default_prov = Provider(provider_row.provider) if provider_row else Provider.anthropic

    # Delete existing config rows for this org
    existing = (
        await db.execute(
            select(OrgLLMTaskConfig).where(
                OrgLLMTaskConfig.org_id == current_user.org_id
            )
        )
    ).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()

    if body.preset == "balanced":
        # Use defaults — no rows needed (factory falls through to DEFAULT_TASK_SPECS)
        await _audit(db, current_user.org_id, current_user.id, "apply_preset", {"preset": "balanced"})
        await db.commit()
        return {"preset": "balanced", "tasks_configured": 0}

    if body.preset in ("smart", "cheap"):
        model_map = _SMART_MODELS if body.preset == "smart" else _CHEAP_MODELS
        for task in TaskType:
            db.add(OrgLLMTaskConfig(
                org_id=current_user.org_id,
                task_type=task.value,
                provider=default_prov.value,
                model=model_map[default_prov],
                max_tokens=None,
                temperature=None,
            ))
        await _audit(db, current_user.org_id, current_user.id, "apply_preset", {"preset": body.preset, "provider": default_prov.value})
        await db.commit()
        return {"preset": body.preset, "tasks_configured": len(list(TaskType))}

    # Custom mode
    if body.custom:
        for task_str, spec in body.custom.items():
            try:
                TaskType(task_str)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unknown task type: {task_str}")
            try:
                Provider(spec.provider)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unknown provider: {spec.provider}")
            db.add(OrgLLMTaskConfig(
                org_id=current_user.org_id,
                task_type=task_str,
                provider=spec.provider,
                model=spec.model,
                max_tokens=spec.max_tokens,
                temperature=spec.temperature,
            ))
        await _audit(db, current_user.org_id, current_user.id, "set_task_config", {"tasks": list(body.custom.keys())})
        await db.commit()
        return {"preset": "custom", "tasks_configured": len(body.custom)}

    raise HTTPException(status_code=400, detail="Invalid request")


@router.get("/usage")
async def get_usage(
    since: str | None = None,
    group_by: str = "task",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return aggregated usage for the caller's org."""
    from sqlalchemy import cast, Date

    query = select(
        LLMUsageEvent.task,
        LLMUsageEvent.provider,
        LLMUsageEvent.model,
        func.sum(LLMUsageEvent.input_tokens).label("input_tokens"),
        func.sum(LLMUsageEvent.output_tokens).label("output_tokens"),
        func.sum(LLMUsageEvent.cost_usd).label("cost_usd"),
        func.count().label("calls"),
    ).where(LLMUsageEvent.org_id == current_user.org_id)

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.where(LLMUsageEvent.created_at >= since_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="since must be ISO datetime")

    query = query.group_by(LLMUsageEvent.task, LLMUsageEvent.provider, LLMUsageEvent.model)
    rows = (await db.execute(query)).all()

    total_cost = sum(float(r.cost_usd) for r in rows)
    return {
        "total_cost_usd": round(total_cost, 6),
        "rows": [
            {
                "task": r.task,
                "provider": r.provider,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": float(r.cost_usd),
                "calls": r.calls,
            }
            for r in rows
        ],
    }


@router.get("/latency-stats")
async def get_latency_stats(
    since: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-task-type LLM latency percentiles (p50/p95/avg/min/max) and token
    distribution, computed from LLMUsageEvent.duration_ms for the caller's org."""
    from app.brain.usage_stats import aggregate_latency_stats

    query = select(
        LLMUsageEvent.task,
        LLMUsageEvent.duration_ms,
        LLMUsageEvent.input_tokens,
        LLMUsageEvent.output_tokens,
    ).where(LLMUsageEvent.org_id == current_user.org_id)

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.where(LLMUsageEvent.created_at >= since_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="since must be ISO datetime")

    rows = (await db.execute(query)).all()
    row_dicts = [
        {
            "task": r.task,
            "duration_ms": r.duration_ms,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
        }
        for r in rows
    ]
    stats = aggregate_latency_stats(row_dicts)
    return {
        "tasks": stats,
        "total_calls": sum(s["calls"] for s in stats),
    }


@router.get("/audit")
async def get_audit_log(
    limit: int = 100,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return audit log entries for the caller's org."""
    rows = (
        await db.execute(
            select(OrgLLMAuditLog)
            .where(OrgLLMAuditLog.org_id == current_user.org_id)
            .order_by(OrgLLMAuditLog.created_at.desc())
            .limit(min(limit, 500))
        )
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "user_id": str(row.user_id) if row.user_id else None,
            "action": row.action,
            "payload": row.payload,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


# ── Budget management ─────────────────────────────────────────────────────────

class BudgetSetRequest(BaseModel):
    monthly_limit_usd: float
    reset_day: int = 1
    alert_threshold_pct: int = 80
    hard_cap: bool = True


@router.get("/budget")
async def get_budget(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.org_llm import OrgBudget
    if current_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    row = (await db.execute(
        select(OrgBudget).where(OrgBudget.org_id == current_user.org_id)
    )).scalar_one_or_none()
    if row is None:
        return {"configured": False, "unlimited": True}
    pct_used = (row.current_spend_usd / row.monthly_limit_usd * 100) if row.monthly_limit_usd else 0
    return {
        "configured": True,
        "monthly_limit_usd": float(row.monthly_limit_usd),
        "current_spend_usd": float(row.current_spend_usd),
        "pct_used": round(pct_used, 2),
        "alert_threshold_pct": row.alert_threshold_pct,
        "hard_cap": row.hard_cap,
        "reset_day": row.reset_day,
    }


@router.put("/budget")
async def set_budget(
    body: BudgetSetRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.org_llm import OrgBudget
    if current_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    if not (1 <= body.reset_day <= 28):
        raise HTTPException(status_code=422, detail="reset_day must be 1–28")
    row = (await db.execute(
        select(OrgBudget).where(OrgBudget.org_id == current_user.org_id)
    )).scalar_one_or_none()
    if row is None:
        row = OrgBudget(
            org_id=current_user.org_id,
            monthly_limit_usd=body.monthly_limit_usd,
            alert_threshold_pct=body.alert_threshold_pct,
            hard_cap=body.hard_cap,
            reset_day=body.reset_day,
        )
        db.add(row)
    else:
        row.monthly_limit_usd = body.monthly_limit_usd
        row.alert_threshold_pct = body.alert_threshold_pct
        row.hard_cap = body.hard_cap
        row.reset_day = body.reset_day
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "monthly_limit_usd": float(row.monthly_limit_usd)}


@router.delete("/budget")
async def delete_budget(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.org_llm import OrgBudget
    from sqlalchemy import delete as sa_delete
    if current_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    await db.execute(sa_delete(OrgBudget).where(OrgBudget.org_id == current_user.org_id))
    await db.commit()
    return {"ok": True}


@router.post("/budget/reset")
async def reset_budget(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.org_llm import OrgBudget
    if current_user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no organization")
    row = (await db.execute(
        select(OrgBudget).where(OrgBudget.org_id == current_user.org_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No budget configured")
    row.current_spend_usd = 0.0
    await db.commit()
    return {"ok": True, "reset": True}
