# backend/app/api/start.py
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.database import get_db, AsyncSessionLocal
from app.models.engagement import Engagement, EngagementStatus
from app.models.finding import Finding, Severity, ValidationStatus
from app.models.task import Task, TaskStatus, Priority
from app.models.agent import Agent, AgentType, AgentStatus
from app.ws import progress as ws_progress

router = APIRouter(prefix="/api/v1/engagements", tags=["orchestration"])


# Map severity strings to enum values
_SEVERITY_MAP = {
    "critical": Severity.critical,
    "high": Severity.high,
    "medium": Severity.medium,
    "low": Severity.low,
    "info": Severity.info,
}


async def _broadcast(engagement_id: str, event_type: str, payload: dict) -> None:
    await ws_progress.broadcast(engagement_id, event_type, payload)


async def _ensure_placeholder_task_agent(
    db: AsyncSession,
    engagement_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create and persist a placeholder Task + Agent so findings have FK parents.

    The Finding model requires non-null task_id/agent_id. Plan 5's codebase
    pipeline runs standalone agents that don't go through the bidding/task
    flow, so we create minimal placeholder rows.
    """
    agent = Agent(
        engagement_id=engagement_id,
        type=AgentType.recon,
        spawned_reason="plan5 orchestration placeholder",
        status=AgentStatus.running,
        tools=["plan5_pipeline"],
    )
    db.add(agent)
    await db.flush()

    task_row = Task(
        engagement_id=engagement_id,
        title="Plan 5 pipeline task",
        description="Placeholder task for codebase pipeline findings",
        surface="local",
        priority=Priority.medium,
        status=TaskStatus.assigned,
        created_by=agent.id,
    )
    db.add(task_row)
    await db.flush()
    return task_row.id, agent.id


async def _judge_findings_async(engagement_id_str: str, finding_ids: list[uuid.UUID]) -> None:
    """Background-task: grade a batch of findings via the LLM judge, persist verdicts,
    and broadcast `finding_judged` events so the UI updates live."""
    if not finding_ids:
        return
    from app.brain.findings_judge import FindingsJudge
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Finding).where(Finding.id.in_(finding_ids)))
            findings = list(result.scalars().all())
            payload = [
                {
                    "id": str(f.id),
                    "vulnerability_class": f.vulnerability_class,
                    "severity": f.severity.value,
                    "affected_surface": f.affected_surface,
                    "description": f.description,
                    "evidence": f.evidence,
                }
                for f in findings
            ]
            judge = FindingsJudge()
            verdicts = await judge.judge(payload)

            by_id = {v.get("id"): v for v in verdicts}
            for f in findings:
                v = by_id.get(str(f.id))
                if v is None:
                    continue
                f.triage_judgment = {
                    "likely_false_positive": bool(v.get("likely_false_positive", False)),
                    "confidence": float(v.get("confidence", 0.0)),
                    "reasoning": str(v.get("reasoning", ""))[:600],
                    "dedup_signature": str(v.get("dedup_signature", "")),
                    "suggested_severity": v.get("suggested_severity"),
                }
            await db.commit()

            for f in findings:
                if f.triage_judgment is not None:
                    await _broadcast(engagement_id_str, "finding_judged", {
                        "finding_id": str(f.id),
                        "judgment": f.triage_judgment,
                    })
    except Exception as exc:
        logger.exception("findings judge failed for engagement %s: %s", engagement_id_str, exc)


async def _save_finding(
    db: AsyncSession,
    engagement_id: uuid.UUID,
    task_id: uuid.UUID,
    agent_id: uuid.UUID,
    f: dict,
) -> uuid.UUID:
    """Persist a raw finding dict to the DB, conforming to the Finding schema."""
    severity = _SEVERITY_MAP.get(str(f.get("severity", "medium")).lower(), Severity.medium)
    title = str(f.get("vulnerability") or f.get("description") or "Finding")[:200]
    vuln_class = str(f.get("vulnerability", "unknown"))[:100]
    surface = str(f.get("file") or f.get("endpoint") or "unknown")[:500]
    description = str(f.get("description", ""))[:2000]
    evidence_val = f.get("evidence", "")
    evidence_list = evidence_val if isinstance(evidence_val, list) else [str(evidence_val)[:2000]]
    reproduction = f.get("reproduction_steps") or ([f.get("recommendation")] if f.get("recommendation") else [])

    finding = Finding(
        engagement_id=engagement_id,
        task_id=task_id,
        agent_id=agent_id,
        title=title,
        description=description,
        vulnerability_class=vuln_class,
        affected_surface=surface,
        reproduction_steps=list(reproduction),
        evidence=evidence_list,
        severity=severity,
        validation_status=ValidationStatus.pending,
        confidence_score=float(f.get("confidence_score", 0.7)),
    )
    db.add(finding)
    await db.flush()
    return finding.id


async def _run_web_pipeline(engagement_id: uuid.UUID) -> None:
    eid = str(engagement_id)
    async with AsyncSessionLocal() as db:
        engagement = await db.get(Engagement, engagement_id)
        if engagement is None:
            return
        try:
            from app.brain.semantic_modeler import SemanticModeler
            from app.brain.campaign_planner import CampaignPlanner
            from app.knowledge.query import KnowledgeQuery
            from app.swarm.agents.probe import ProbeAgent

            await _broadcast(eid, "agent_started", {"phase": "crawl", "target": engagement.target_url})
            modeler = SemanticModeler()
            crawl_data = await modeler.crawl(engagement.target_url)
            semantic_model = await modeler.build(engagement.target_url, crawl_data)
            engagement.semantic_model = semantic_model
            await db.commit()
            await _broadcast(eid, "agent_completed", {"phase": "crawl", "app_type": semantic_model.get("app_type")})

            kb = KnowledgeQuery()
            kb_context = await kb.find_similar_techniques(
                description=str(semantic_model.get("interesting_surfaces", [])),
                tech_stack=semantic_model.get("tech_stack", []),
            )

            await _broadcast(eid, "agent_started", {"phase": "campaign_planning"})
            planner = CampaignPlanner()
            hypotheses = await planner.generate(semantic_model, kb_context)
            await _broadcast(eid, "agent_completed", {"phase": "campaign_planning", "hypotheses": len(hypotheses)})

            task_id, agent_id = await _ensure_placeholder_task_agent(db, engagement_id)
            await db.commit()

            for hyp in hypotheses[:5]:
                agent = ProbeAgent(
                    agent_id=str(uuid.uuid4()),
                    engagement_id=eid,
                    agent_type="probe",
                    tools=["http_probe"],
                )
                await _broadcast(eid, "agent_started", {"agent_id": agent.agent_id, "hypothesis": hyp.get("title")})
                result = await agent._execute({
                    "target_url": engagement.target_url,
                    "endpoint": hyp.get("surface", "/"),
                    "attack_class": hyp.get("attack_class", ""),
                    "surface": hyp.get("surface", "/"),
                })
                batch_ids: list[uuid.UUID] = []
                for f in result.get("findings", []):
                    fid = await _save_finding(db, engagement_id, task_id, agent_id, f)
                    batch_ids.append(fid)
                    await _broadcast(eid, "finding_discovered", {"finding": f})
                await db.commit()
                if batch_ids:
                    asyncio.create_task(_judge_findings_async(eid, batch_ids))

        except Exception as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        await _finalize(engagement_id, db, eid, success=True)


async def _run_codebase_pipeline(engagement_id: uuid.UUID) -> None:
    eid = str(engagement_id)
    async with AsyncSessionLocal() as db:
        engagement = await db.get(Engagement, engagement_id)
        if engagement is None:
            return

        target_path = engagement.target_path
        if not target_path:
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": "target_path required for local_codebase engagements"})
            await _finalize(engagement_id, db, eid)
            return

        try:
            from app.brain.codebase_modeler import CodebaseModeler
            from app.swarm.agents.code_analyzer import CodeAnalyzerAgent
            from app.swarm.agents.config_auditor import ConfigAuditorAgent
            from app.swarm.agents.dependency_scanner import DependencyScannerAgent
            from app.swarm.agents.fuzzer import FuzzerAgent
            from app.swarm.agents.secret_scanner import SecretScannerAgent

            # Phase 1: Model the codebase
            await _broadcast(eid, "agent_started", {"phase": "codebase_modeling", "path": target_path})
            modeler = CodebaseModeler()
            semantic_model = await modeler.build(target_path, engagement_id=eid)
            engagement.semantic_model = semantic_model
            await db.commit()
            await _broadcast(eid, "agent_completed", {
                "phase": "codebase_modeling",
                "app_type": semantic_model.get("app_type"),
                "attack_surfaces": len(semantic_model.get("attack_surfaces", [])),
            })

            task = {"target_path": target_path, "semantic_model": semantic_model}

            # Phase 2: Run agents in parallel
            agents = [
                CodeAnalyzerAgent(agent_id=str(uuid.uuid4()), engagement_id=eid, agent_type="code_analyzer", tools=["llm_review"]),
                DependencyScannerAgent(agent_id=str(uuid.uuid4()), engagement_id=eid, agent_type="dependency_scanner", tools=["osv_api"]),
                FuzzerAgent(agent_id=str(uuid.uuid4()), engagement_id=eid, agent_type="fuzzer", tools=["subprocess"]),
                SecretScannerAgent(agent_id=str(uuid.uuid4()), engagement_id=eid, agent_type="secret_scanner", tools=["regex"]),
                ConfigAuditorAgent(agent_id=str(uuid.uuid4()), engagement_id=eid, agent_type="config_auditor", tools=["rules"]),
            ]

            for agent in agents:
                await _broadcast(eid, "agent_started", {"agent_id": agent.agent_id, "agent_type": agent.agent_type})

            results = await asyncio.gather(*[a._execute(task) for a in agents], return_exceptions=True)

            task_id, agent_id = await _ensure_placeholder_task_agent(db, engagement_id)
            await db.commit()

            for result in results:
                if isinstance(result, Exception):
                    continue
                if not isinstance(result, dict):
                    continue
                agent_type = result.get("agent_type", "unknown")
                findings = result.get("findings", [])
                await _broadcast(eid, "agent_completed", {"agent_type": agent_type, "findings_count": len(findings)})
                batch_ids: list[uuid.UUID] = []
                for f in findings:
                    fid = await _save_finding(db, engagement_id, task_id, agent_id, f)
                    batch_ids.append(fid)
                    await _broadcast(eid, "finding_discovered", {"finding": f})
                await db.commit()
                if batch_ids:
                    asyncio.create_task(_judge_findings_async(eid, batch_ids))

        except Exception as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        await _finalize(engagement_id, db, eid, success=True)


async def _finalize(engagement_id: uuid.UUID, db: AsyncSession, eid: str, success: bool = True) -> None:
    # Use a fresh session — the pipeline session may be in a stale/dirty state.
    # Engagement.completed_at is a naive TIMESTAMP column, so use naive utcnow().
    try:
        async with AsyncSessionLocal() as fresh_db:
            engagement = await fresh_db.get(Engagement, engagement_id)
            if engagement is not None:
                engagement.status = EngagementStatus.complete if success else EngagementStatus.pending
                if success:
                    engagement.completed_at = datetime.utcnow()
                await fresh_db.commit()
    except Exception as exc:
        logger.exception("finalize failed for engagement %s: %s", eid, exc)
    await _broadcast(eid, "campaign_complete", {"status": "done" if success else "error", "engagement_id": eid})


@router.post("/{engagement_id}/start", status_code=202)
async def start_engagement(
    engagement_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    engagement = await db.get(Engagement, engagement_id)
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    if engagement.status == EngagementStatus.running:
        raise HTTPException(status_code=409, detail="Engagement already running")

    engagement.status = EngagementStatus.running
    await db.commit()

    target_type = engagement.target_type
    if target_type in ("local_codebase", "binary"):
        background_tasks.add_task(_run_codebase_pipeline, engagement_id)
    else:
        background_tasks.add_task(_run_web_pipeline, engagement_id)

    return {
        "status": "started",
        "engagement_id": str(engagement_id),
        "target_type": target_type,
    }
