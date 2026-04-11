# backend/app/api/start.py
from __future__ import annotations
import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.models.engagement import Engagement, EngagementStatus
from app.models.finding import Finding, Severity, ValidationStatus
from app.models.task import Task, TaskStatus, Priority
from app.models.agent import Agent, AgentType, AgentStatus
from app.ws.stream import stream_manager

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
    await stream_manager.broadcast(engagement_id, {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


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


async def _save_finding(
    db: AsyncSession,
    engagement_id: uuid.UUID,
    task_id: uuid.UUID,
    agent_id: uuid.UUID,
    f: dict,
) -> None:
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
                for f in result.get("findings", []):
                    await _save_finding(db, engagement_id, task_id, agent_id, f)
                    await _broadcast(eid, "finding_discovered", {"finding": f})
                await db.commit()

        except Exception as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": str(e)})
        finally:
            await _finalize(engagement_id, db, eid)


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
            from app.swarm.agents.dependency_scanner import DependencyScannerAgent
            from app.swarm.agents.fuzzer import FuzzerAgent

            # Phase 1: Model the codebase
            await _broadcast(eid, "agent_started", {"phase": "codebase_modeling", "path": target_path})
            modeler = CodebaseModeler()
            semantic_model = await modeler.build(target_path)
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
                for f in findings:
                    await _save_finding(db, engagement_id, task_id, agent_id, f)
                    await _broadcast(eid, "finding_discovered", {"finding": f})
                await db.commit()

        except Exception as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": str(e)})
        finally:
            await _finalize(engagement_id, db, eid)


async def _finalize(engagement_id: uuid.UUID, db: AsyncSession, eid: str) -> None:
    try:
        engagement = await db.get(Engagement, engagement_id)
        if engagement is not None:
            engagement.status = EngagementStatus.complete
            engagement.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:
        await db.rollback()
    await _broadcast(eid, "campaign_complete", {"status": "done", "engagement_id": eid})


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
