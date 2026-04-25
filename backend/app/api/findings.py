from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.finding import Finding, TriageStatus, ValidationStatus
from app.models.engagement import Engagement
from app.brain.exploit_engine import ExploitEngine
from app.brain.poc_engine import PoCEngine
from app.brain.exploit_script_engine import ExploitScriptEngine
from app.brain.exploit_executor import ExploitExecutor
from app.brain.execution_judge import ExecutionJudge

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])


class ExecuteRequest(BaseModel):
    confirmed: bool = False


class OverrideVerdictRequest(BaseModel):
    verdict: str


class TriageRequest(BaseModel):
    status: str | None = None
    notes: str | None = None


def _serialize_finding(f: Finding) -> dict:
    return {
        "id": str(f.id),
        "engagement_id": str(f.engagement_id),
        "title": f.title,
        "severity": f.severity.value,
        "vulnerability_class": f.vulnerability_class,
        "affected_surface": f.affected_surface,
        "description": f.description,
        "evidence": f.evidence,
        "confidence_score": f.confidence_score,
        "validation_status": f.validation_status.value,
        "reproduction_steps": f.reproduction_steps,
        "exploit_detail": f.exploit_detail,
        "poc_detail": f.poc_detail,
        "exploit_script": f.exploit_script,
        "exploit_execution": f.exploit_execution,
        "triage_status": f.triage_status.value,
        "triage_notes": f.triage_notes,
        "triage_updated_at": f.triage_updated_at.isoformat() if f.triage_updated_at else None,
        "triage_judgment": f.triage_judgment,
        "created_at": f.created_at.isoformat(),
    }


@router.get("/{finding_id}")
async def get_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _serialize_finding(finding)


@router.patch("/{finding_id}/triage")
async def triage_finding(
    finding_id: uuid.UUID,
    payload: TriageRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import datetime
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if payload.status is not None:
        try:
            finding.triage_status = TriageStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid triage status: {payload.status}")
    if payload.notes is not None:
        finding.triage_notes = payload.notes[:2000]
    finding.triage_updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(finding)
    return _serialize_finding(finding)


@router.post("/{finding_id}/exploit")
async def generate_exploit(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.exploit_detail:
        return finding.exploit_detail

    engagement = await db.get(Engagement, finding.engagement_id)
    context = {
        "target_url": engagement.target_url if engagement else None,
        "target_path": engagement.target_path if engagement else None,
        "target_type": engagement.target_type if engagement else "web",
        "app_type": (engagement.semantic_model or {}).get("app_type", "unknown") if engagement else "unknown",
    }

    engine = ExploitEngine()
    exploit = await engine.generate(_serialize_finding(finding), context)

    finding.exploit_detail = exploit
    await db.commit()
    return exploit


@router.get("/{finding_id}/poc")
async def get_poc(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"poc_detail": finding.poc_detail}


@router.post("/{finding_id}/poc")
async def generate_poc(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.poc_detail:
        return finding.poc_detail

    engagement = await db.get(Engagement, finding.engagement_id)
    context = {
        "target_url": engagement.target_url if engagement else None,
        "target_path": engagement.target_path if engagement else None,
        "target_type": engagement.target_type if engagement else "web",
        "app_type": (engagement.semantic_model or {}).get("app_type", "unknown") if engagement else "unknown",
    }

    engine = PoCEngine()
    poc = await engine.generate(_serialize_finding(finding), context)

    finding.poc_detail = poc
    await db.commit()
    return poc


# ── Plan 11: Live Exploitation endpoints ─────────────────────────────────────

@router.post("/{finding_id}/exploit/generate")
async def generate_exploit_script(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate (or return cached) weaponized exploit script."""
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.exploit_script:
        return finding.exploit_script

    engagement = await db.get(Engagement, finding.engagement_id)
    context = {
        "target_url": engagement.target_url if engagement else None,
        "target_path": engagement.target_path if engagement else None,
        "target_type": engagement.target_type if engagement else "web",
        "app_type": (engagement.semantic_model or {}).get("app_type", "unknown") if engagement else "unknown",
    }

    engine = ExploitScriptEngine()
    script_data = await engine.generate(_serialize_finding(finding), context)

    finding.exploit_script = script_data
    await db.commit()
    return script_data


@router.post("/{finding_id}/exploit/execute")
async def execute_exploit(
    finding_id: uuid.UUID,
    body: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Execute the weaponized exploit script against the real target.

    Requires body: {"confirmed": true} — without it returns a confirmation prompt.
    """
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if not body.confirmed:
        engagement = await db.get(Engagement, finding.engagement_id)
        target = (
            (engagement.target_url if engagement else None)
            or (engagement.target_path if engagement else None)
            or "unknown"
        )
        impact = (finding.exploit_script or {}).get("impact_achieved", "Unknown impact")
        return {
            "requires_confirmation": True,
            "target": target,
            "impact_achieved": impact,
        }

    # Auto-generate exploit script if not cached
    if not finding.exploit_script:
        engagement = await db.get(Engagement, finding.engagement_id)
        context = {
            "target_url": engagement.target_url if engagement else None,
            "target_path": engagement.target_path if engagement else None,
            "target_type": engagement.target_type if engagement else "web",
            "app_type": (engagement.semantic_model or {}).get("app_type", "unknown") if engagement else "unknown",
        }
        engine = ExploitScriptEngine()
        finding.exploit_script = await engine.generate(_serialize_finding(finding), context)
        await db.commit()

    script_data = finding.exploit_script

    # Execute in Docker
    executor = ExploitExecutor()
    execution_result = await executor.execute(
        script=script_data["script"],
        language=script_data.get("language", "python"),
        setup=script_data.get("setup", []),
        timeout=60,
    )

    # Judge the result
    judge = ExecutionJudge()
    verdict_result = await judge.judge(
        finding=_serialize_finding(finding),
        script=script_data["script"],
        stdout=execution_result["stdout"],
        stderr=execution_result["stderr"],
        exit_code=execution_result["exit_code"],
    )

    # Persist
    full_execution: dict[str, Any] = {
        **execution_result,
        "verdict": verdict_result["verdict"],
        "confidence": verdict_result["confidence"],
        "reasoning": verdict_result["reasoning"],
        "override_verdict": None,
    }
    finding.exploit_execution = full_execution

    # Update validation_status if exploitation confirmed
    if verdict_result["verdict"] == "confirmed":
        finding.validation_status = ValidationStatus.confirmed

    await db.commit()
    return full_execution


@router.patch("/{finding_id}/exploit/execution")
async def override_verdict(
    finding_id: uuid.UUID,
    body: OverrideVerdictRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Override the LLM verdict with a user-supplied verdict."""
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if not finding.exploit_execution:
        raise HTTPException(status_code=404, detail="No execution result found — run exploit first")

    allowed = {"confirmed", "failed", "inconclusive"}
    if body.verdict not in allowed:
        raise HTTPException(status_code=422, detail=f"verdict must be one of: {allowed}")

    updated = {**finding.exploit_execution, "override_verdict": body.verdict}
    finding.exploit_execution = updated
    await db.commit()
    return updated
