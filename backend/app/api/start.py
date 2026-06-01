# backend/app/api/start.py
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from sqlalchemy import select, update

from app.api.deps import require_analyst
from app.brain.llm_factory import BudgetExceededError, RateLimitQueuedError
from app.brain.os_modeler import OSModeler, SSHAuth
from app.brain.os_fingerprint import OSFingerprint
from app.database import get_db, AsyncSessionLocal
from app.models.engagement import Engagement, EngagementStatus
from app.models.os_target import OSTarget
from app.models.user import User
from app.models.finding import Finding, Severity, ValidationStatus
from app.models.task import Task, TaskStatus, Priority
from app.models.agent import Agent, AgentType, AgentStatus
from app.queue import enqueue
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


async def _stamp_agent_duration(
    db: AsyncSession,
    agent_id: uuid.UUID,
    started_at: datetime,
) -> None:
    """Record completion time and duration_ms on the agent row."""
    now = datetime.utcnow()
    ms = max(0, int((now - started_at).total_seconds() * 1000))
    await db.execute(
        update(Agent)
        .where(Agent.id == agent_id)
        .values(completed_at=now, duration_ms=ms, status=AgentStatus.completed)
    )


async def _judge_findings_async(
    engagement_id_str: str,
    finding_ids: list[uuid.UUID],
    org_id: uuid.UUID | None = None,
) -> None:
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
            judge = FindingsJudge(org_id=org_id)
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
            modeler = SemanticModeler(org_id=engagement.org_id)
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
            planner = CampaignPlanner(org_id=engagement.org_id)
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
                    await enqueue("judge_findings", eid, [str(fid) for fid in batch_ids], str(engagement.org_id))

        except BudgetExceededError as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "budget_exceeded", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        except RateLimitQueuedError as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "rate_limited", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        except Exception as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        await _finalize(engagement_id, db, eid, success=True)


async def _run_github_pipeline(engagement_id: uuid.UUID) -> None:
    """Clone a GitHub repo to a temp dir, set target_path, then run the codebase pipeline."""
    import shutil
    import tempfile
    eid = str(engagement_id)
    tmp_dir: str | None = None
    async with AsyncSessionLocal() as db:
        engagement = await db.get(Engagement, engagement_id)
        if engagement is None:
            return

        repo_url = (engagement.target_url or "").strip()
        branch = (engagement.target_path or "main").strip() or "main"

        if not repo_url:
            await _broadcast(eid, "campaign_complete", {
                "status": "error",
                "error": "target_url (GitHub repo URL) is required for github engagements",
            })
            await _finalize(engagement_id, db, eid, success=False)
            return

        try:
            tmp_dir = tempfile.mkdtemp(prefix="forge_github_")
            await _broadcast(eid, "agent_started", {"phase": "clone", "repo": repo_url, "branch": branch})

            proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "1", "--branch", branch, repo_url, tmp_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            except asyncio.TimeoutError:
                proc.kill()
                await _broadcast(eid, "campaign_complete", {"status": "error", "error": "git clone timed out"})
                await _finalize(engagement_id, db, eid, success=False)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return

            if proc.returncode != 0:
                err = stderr.decode(errors="replace")[:500]
                await _broadcast(eid, "campaign_complete", {"status": "error", "error": f"git clone failed: {err}"})
                await _finalize(engagement_id, db, eid, success=False)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return

            engagement.target_path = tmp_dir
            await db.commit()
            await _broadcast(eid, "agent_completed", {"phase": "clone", "path": tmp_dir})

        except Exception as e:
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": f"clone error: {e}"})
            await _finalize(engagement_id, db, eid, success=False)
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            return

    try:
        await _run_codebase_pipeline(engagement_id)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


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
            modeler = CodebaseModeler(org_id=engagement.org_id)
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
                    # Match _save_finding's default so the live stream and DB agree.
                    f.setdefault("confidence_score", 0.7)
                    fid = await _save_finding(db, engagement_id, task_id, agent_id, f)
                    batch_ids.append(fid)
                    await _broadcast(eid, "finding_discovered", {"finding": {**f, "id": str(fid)}})
                await db.commit()
                if batch_ids:
                    await enqueue("judge_findings", eid, [str(fid) for fid in batch_ids], str(engagement.org_id))

        except BudgetExceededError as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "budget_exceeded", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        except RateLimitQueuedError as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "rate_limited", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        except Exception as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        await _finalize(engagement_id, db, eid, success=True)


async def _run_cve_pipeline(engagement_id: uuid.UUID) -> None:
    """CVE-driven pipeline.

    Input is a CVE / GHSA id stored in engagement.target_url. The pipeline:
      1. Researches the advisory (OSV → NVD).
      2. Synthesises a Finding from the advisory metadata.
      3. Generates a weaponized exploit script (research already cached so no
         duplicate fetch).
      4. Runs the differential test (vuln vs first-fixed) and judges the diff.
      5. campaign_complete.
    """
    eid = str(engagement_id)
    async with AsyncSessionLocal() as db:
        engagement = await db.get(Engagement, engagement_id)
        if engagement is None:
            return

        cve_id = (engagement.target_url or "").strip()
        if not cve_id:
            await _broadcast(eid, "campaign_complete", {"status": "error", "error": "target_url must be a CVE or GHSA id for cve engagements"})
            await _finalize(engagement_id, db, eid, success=False)
            return

        try:
            from app.brain.researcher import Researcher
            from app.brain.exploit_script_engine import ExploitScriptEngine
            from app.brain.exploit_executor import ExploitExecutor
            from app.brain.execution_judge import ExecutionJudge

            await _broadcast(eid, "agent_started", {"phase": "cve_research", "cve": cve_id})
            researcher = Researcher()
            seed = {"description": cve_id, "evidence": [cve_id]}
            research = await researcher.research(seed)
            engagement.semantic_model = {"app_type": "cve", "research": research}
            await db.commit()

            advisories = research.get("advisories") or []
            if not advisories:
                await _broadcast(eid, "campaign_complete", {"status": "error", "error": f"no advisory found for {cve_id} in OSV/NVD"})
                await _finalize(engagement_id, db, eid, success=False)
                return

            top = advisories[0]
            ranges = research.get("ranges") or []
            primary_pkg = next((r.get("package") for r in ranges if r.get("package")), "unknown")
            first_fixed = research.get("first_fixed") or "unknown"
            await _broadcast(eid, "agent_completed", {
                "phase": "cve_research",
                "advisory": top.get("id", cve_id),
                "package": primary_pkg,
                "first_fixed": first_fixed,
            })

            # Synthesise a Finding from the advisory
            task_id, agent_id = await _ensure_placeholder_task_agent(db, engagement_id)
            await db.commit()

            severity = "high" if first_fixed != "unknown" else "medium"
            synthetic = {
                "vulnerability": "known_cve",
                "vulnerability_class": "known_cve",
                "severity": severity,
                "title": top.get("id", cve_id),
                "description": (top.get("summary") or top.get("details") or f"Advisory {cve_id}")[:1500],
                "evidence": [
                    f"Advisory: {top.get('id', cve_id)}",
                    f"Package: {primary_pkg}",
                    f"First fixed: {first_fixed}",
                    *[f"Fix ref: {u}" for u in (research.get("fix_refs") or [])[:3]],
                ],
                "recommendation": f"Upgrade {primary_pkg} to {first_fixed}",
                "osv_id": top.get("id", cve_id),
                "file": "requirements.txt",
                "package": primary_pkg,
                "version": next((r.get("introduced") for r in ranges if r.get("introduced")), "unknown"),
                "confidence_score": 0.9,
            }
            finding_db_id = await _save_finding(db, engagement_id, task_id, agent_id, synthetic)

            # Cache the research bundle on the persisted finding so script gen reuses it
            from sqlalchemy import select
            row = (await db.execute(select(Finding).where(Finding.id == finding_db_id))).scalar_one()
            row.research = research
            await db.commit()

            await _broadcast(eid, "finding_discovered", {"finding": synthetic})
            await enqueue("judge_findings", eid, [str(finding_db_id)], str(engagement.org_id))

            # Generate the weaponized exploit script
            await _broadcast(eid, "agent_started", {"phase": "exploit_script_gen", "advisory": top.get("id", cve_id)})
            script_engine = ExploitScriptEngine(org_id=engagement.org_id)
            context = {
                "target_url": cve_id,
                "target_path": None,
                "target_type": "cve",
                "app_type": "cve",
            }
            # Re-fetch the row to get a serializable form
            row = (await db.execute(select(Finding).where(Finding.id == finding_db_id))).scalar_one()
            from app.api.findings import _serialize_finding
            script_data = await script_engine.generate(_serialize_finding(row), context, research=research)
            row.exploit_script = script_data
            await db.commit()
            await _broadcast(eid, "agent_completed", {
                "phase": "exploit_script_gen",
                "language": script_data.get("language"),
                "patched_label": script_data.get("patched_label"),
            })

            # Differential test (vuln vs patched)
            patched_setup = script_data.get("patched_setup") or []
            if not patched_setup:
                await _broadcast(eid, "campaign_complete", {"status": "error", "error": "ExploitScriptEngine did not produce patched_setup — diff test skipped"})
                await _finalize(engagement_id, db, eid, success=False)
                return

            await _broadcast(eid, "agent_started", {"phase": "diff_execute", "patched_label": script_data.get("patched_label")})
            executor = ExploitExecutor()
            vuln_run = await executor.execute(
                script=script_data["script"],
                language=script_data.get("language", "python"),
                setup=script_data.get("setup", []),
                timeout=90,
            )
            patched_run = await executor.execute(
                script=script_data["script"],
                language=script_data.get("language", "python"),
                setup=patched_setup,
                timeout=90,
            )

            judge = ExecutionJudge(org_id=engagement.org_id)
            row = (await db.execute(select(Finding).where(Finding.id == finding_db_id))).scalar_one()
            verdict = await judge.judge_diff(
                finding=_serialize_finding(row),
                script=script_data["script"],
                vuln_stdout=vuln_run["stdout"],
                vuln_stderr=vuln_run["stderr"],
                vuln_exit=vuln_run["exit_code"],
                patched_stdout=patched_run["stdout"],
                patched_stderr=patched_run["stderr"],
                patched_exit=patched_run["exit_code"],
                patched_label=script_data.get("patched_label", "patched version"),
            )

            row.exploit_execution_diff = {
                "patched_label": script_data.get("patched_label", ""),
                "vuln_run": vuln_run,
                "patched_run": patched_run,
                "verdict": verdict.get("verdict"),
                "confidence": verdict.get("confidence"),
                "reasoning": verdict.get("reasoning"),
                "vuln_succeeded": verdict.get("vuln_succeeded"),
                "patched_blocked": verdict.get("patched_blocked"),
            }
            if verdict.get("verdict") == "confirmed":
                row.validation_status = ValidationStatus.confirmed
            await db.commit()

            await _broadcast(eid, "agent_completed", {
                "phase": "diff_execute",
                "verdict": verdict.get("verdict"),
                "confidence": verdict.get("confidence"),
            })

        except BudgetExceededError as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "budget_exceeded", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        except RateLimitQueuedError as e:
            await db.rollback()
            await _broadcast(eid, "campaign_complete", {"status": "rate_limited", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
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
                engagement.status = EngagementStatus.complete if success else EngagementStatus.aborted
                if success:
                    engagement.completed_at = datetime.utcnow()
                await fresh_db.commit()
    except Exception as exc:
        logger.exception("finalize failed for engagement %s: %s", eid, exc)
    await _broadcast(eid, "campaign_complete", {"status": "done" if success else "error", "engagement_id": eid})


_NON_STARTABLE = (
    EngagementStatus.running,
    EngagementStatus.complete,
    EngagementStatus.aborted,
)


@router.post("/{engagement_id}/start", status_code=202)
async def start_engagement(
    engagement_id: uuid.UUID,
    _: User = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    # Atomic status transition: succeeds only when status is NOT already
    # running/complete/aborted.  Two concurrent requests racing here will
    # both hit this UPDATE; exactly one will update 1 row, the other 0 rows.
    result = await db.execute(
        update(Engagement)
        .where(
            Engagement.id == engagement_id,
            Engagement.status.not_in(_NON_STARTABLE),
        )
        .values(
            status=EngagementStatus.running,
            started_at=datetime.utcnow().replace(tzinfo=None),
        )
        .returning(Engagement.target_type, Engagement.org_id)
    )
    row = result.one_or_none()

    if row is None:
        # 0 rows updated — either engagement missing or already in a non-startable state
        existing = await db.get(Engagement, engagement_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Engagement not found")
        raise HTTPException(
            status_code=409,
            detail=f"Engagement cannot be started (status: {existing.status.value})",
        )

    await db.commit()

    target_type, org_id = row
    if target_type == "cve":
        job_name = "run_cve_pipeline"
    elif target_type == "github":
        job_name = "run_github_pipeline"
    elif target_type in ("local_codebase", "binary"):
        job_name = "run_codebase_pipeline"
    elif target_type == "os":
        job_name = "run_os_pipeline"
    else:
        job_name = "run_web_pipeline"

    if target_type == "os":
        job = await enqueue(job_name, str(engagement_id), str(org_id) if org_id else None)
    else:
        job = await enqueue(job_name, str(engagement_id))
    # Persist job_id so the lifespan sweep can detect a crashed worker.
    if job is not None:
        await db.execute(
            update(Engagement)
            .where(Engagement.id == engagement_id)
            .values(job_id=job.job_id)
        )
        await db.commit()

    return {
        "status": "started",
        "engagement_id": str(engagement_id),
        "target_type": target_type,
        "job": job_name,
        "job_id": job.job_id if job is not None else None,
    }


async def _run_os_pipeline(engagement_id: uuid.UUID, org_id: uuid.UUID | None = None) -> None:
    """SSH fingerprint collection + 5 parallel OS security agents + finding persistence."""
    from app.swarm.agents.privesc_agent import PrivescAgent
    from app.swarm.agents.service_audit_agent import ServiceAuditAgent
    from app.swarm.agents.package_vuln_agent import PackageVulnAgent
    from app.swarm.agents.config_audit_agent import OSConfigAuditAgent
    from app.swarm.agents.network_exposure_agent import NetworkExposureAgent

    eid = str(engagement_id)

    async with AsyncSessionLocal() as db:
        target = (await db.execute(
            select(OSTarget).where(OSTarget.engagement_id == engagement_id)
        )).scalar_one_or_none()
        if target is None:
            logger.warning("os_pipeline: no OSTarget for engagement %s", engagement_id)
            return

        key_mat = None
        if target.encrypted_credential:
            try:
                from app.brain.llm_factory import _decrypt_key
                key_mat = _decrypt_key(target.encrypted_credential)
            except Exception:
                logger.warning("os_pipeline: could not decrypt credential for %s", engagement_id)

        auth = SSHAuth(
            auth_type=target.auth_type,
            key_path=key_mat if target.auth_type == "key" else None,
            password=key_mat if target.auth_type == "password" else None,
        )

        await _broadcast(eid, "os_modeling_started", {"host": target.host})
        try:
            modeler = OSModeler()
            fp = await modeler.collect(target.host, target.port, target.username, auth)
            target.fingerprint = fp.to_dict()
            target.collected_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await db.commit()
            await _broadcast(eid, "os_modeling_complete", {
                "host": target.host,
                "packages": len(fp.packages),
                "open_ports": len(fp.open_ports),
                "suid_count": len(fp.suid_binaries),
                "errors": len(fp.collection_errors),
            })
        except Exception as e:
            logger.exception("os_pipeline: fingerprint collection failed for %s", engagement_id)
            await _broadcast(eid, "os_modeling_failed", {"error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return

        try:
            # Create placeholder task + agent rows for FK references
            task_id, agent_id = await _ensure_placeholder_task_agent(db, engagement_id)
            await db.commit()

            fp_dict = fp.to_dict()
            agent_task = {
                "fingerprint": fp_dict,
                "org_id": str(org_id) if org_id else None,
            }

            def _make_agent(cls, atype):
                return cls(
                    agent_id=str(uuid.uuid4()),
                    engagement_id=eid,
                    agent_type=atype,
                    tools=[],
                )

            agents = [
                _make_agent(PrivescAgent, "privesc"),
                _make_agent(ServiceAuditAgent, "service_audit"),
                _make_agent(PackageVulnAgent, "package_vuln"),
                _make_agent(OSConfigAuditAgent, "config_audit"),
                _make_agent(NetworkExposureAgent, "network_exposure"),
            ]

            await _broadcast(eid, "os_agents_started", {"agents": [a.agent_type for a in agents]})

            pipeline_start = datetime.utcnow()
            results = await asyncio.gather(
                *[agent._execute(agent_task) for agent in agents],
                return_exceptions=True,
            )

            all_finding_ids: list[uuid.UUID] = []
            for agent, result in zip(agents, results):
                if isinstance(result, Exception):
                    logger.exception("os_pipeline: agent %s failed", agent.agent_type)
                    await _broadcast(eid, "os_agent_failed", {
                        "agent_type": agent.agent_type,
                        "error": str(result),
                    })
                    continue

                batch_ids: list[uuid.UUID] = []
                for f in result.get("findings", []):
                    fid = await _save_finding(db, engagement_id, task_id, agent_id, f)
                    batch_ids.append(fid)
                    await _broadcast(eid, "finding_discovered", {"finding": f, "agent": agent.agent_type})

                await db.commit()
                all_finding_ids.extend(batch_ids)

                await _broadcast(eid, "os_agent_complete", {
                    "agent_type": agent.agent_type,
                    "findings": len(batch_ids),
                })

            await _stamp_agent_duration(db, agent_id, pipeline_start)
            await db.commit()

            # Collect all raw findings for chain discovery
            all_raw_findings: list[dict] = []
            for result in results:
                if isinstance(result, Exception) or not isinstance(result, dict):
                    continue
                all_raw_findings.extend(result.get("findings", []))

            # Run ChainDiscoveryAgent
            if all_raw_findings:
                from app.swarm.agents.chain_discovery_agent import ChainDiscoveryAgent
                chain_agent = _make_agent(ChainDiscoveryAgent, "chain_discovery")
                await _broadcast(eid, "os_agent_started", {"agent_type": "chain_discovery"})
                try:
                    chain_result = await chain_agent._execute({
                        "findings": all_raw_findings,
                        "org_id": str(org_id) if org_id else None,
                    })
                    chain_batch_ids: list[uuid.UUID] = []
                    for f in chain_result.get("findings", []):
                        fid = await _save_finding(db, engagement_id, task_id, agent_id, f)
                        chain_batch_ids.append(fid)
                        await _broadcast(eid, "finding_discovered", {"finding": f, "agent": "chain_discovery"})
                    await db.commit()
                    all_finding_ids.extend(chain_batch_ids)
                    await _broadcast(eid, "os_agent_complete", {
                        "agent_type": "chain_discovery",
                        "findings": len(chain_batch_ids),
                    })
                except Exception:
                    logger.exception("os_pipeline: ChainDiscoveryAgent failed")

            if all_finding_ids:
                await enqueue("judge_findings", eid, [str(fid) for fid in all_finding_ids],
                              str(org_id) if org_id else None)

            await _broadcast(eid, "os_pipeline_complete", {
                "total_findings": len(all_finding_ids),
                "host": target.host,
            })
        except BudgetExceededError as e:
            await db.rollback()
            await _broadcast(eid, "os_pipeline_complete", {"status": "budget_exceeded", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        except RateLimitQueuedError as e:
            await db.rollback()
            await _broadcast(eid, "os_pipeline_complete", {"status": "rate_limited", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        except Exception as e:
            await db.rollback()
            await _broadcast(eid, "os_pipeline_complete", {"status": "error", "error": str(e)})
            await _finalize(engagement_id, db, eid, success=False)
            return
        await _finalize(engagement_id, db, eid, success=True)


class OSTargetRequest(BaseModel):
    host: str
    port: int = 22
    username: str
    auth_type: str  # key | password | agent
    key_material: str | None = None  # key path or password (will be encrypted)
    access_mode: str = "agentless"
    collector_sudo: bool = False


@router.post("/{engagement_id}/os-target", status_code=201)
async def add_os_target(
    engagement_id: uuid.UUID,
    body: OSTargetRequest,
    current_user: User = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Register an SSH target for OS scanning on this engagement."""
    from app.brain.llm_factory import _encrypt_key, BudgetExceededError
    eng = await db.get(Engagement, engagement_id)
    if eng is None or eng.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Engagement not found")
    if eng.status != EngagementStatus.pending:
        raise HTTPException(status_code=409, detail="Engagement is already running or complete")
    existing_target = (await db.execute(
        select(OSTarget).where(OSTarget.engagement_id == engagement_id)
    )).scalar_one_or_none()
    if existing_target is not None:
        raise HTTPException(status_code=409, detail="OS target already registered for this engagement")
    if body.auth_type not in ("key", "password", "agent"):
        raise HTTPException(status_code=422, detail="auth_type must be key, password, or agent")
    if body.access_mode not in ("agentless", "collector"):
        raise HTTPException(status_code=422, detail="access_mode must be agentless or collector")

    encrypted = None
    if body.key_material:
        try:
            encrypted = _encrypt_key(body.key_material)
        except RuntimeError:
            raise HTTPException(
                status_code=500,
                detail="Server misconfiguration: FORGE_SECRETS_KEY is not set. Contact your administrator.",
            )

    target = OSTarget(
        engagement_id=engagement_id,
        host=body.host,
        port=body.port,
        username=body.username,
        auth_type=body.auth_type,
        encrypted_credential=encrypted,
        access_mode=body.access_mode,
        collector_sudo=body.collector_sudo,
    )
    db.add(target)
    await db.execute(
        update(Engagement)
        .where(Engagement.id == engagement_id)
        .values(status=EngagementStatus.running, started_at=datetime.utcnow().replace(tzinfo=None))
    )
    await db.commit()
    await db.refresh(target)

    job = await enqueue("run_os_pipeline", str(engagement_id), str(eng.org_id) if eng.org_id else None)
    if job is not None:
        await db.execute(
            update(Engagement)
            .where(Engagement.id == engagement_id)
            .values(job_id=job.job_id)
        )
        await db.commit()

    return {
        "id": str(target.id),
        "host": target.host,
        "port": target.port,
        "username": target.username,
        "auth_type": target.auth_type,
        "access_mode": target.access_mode,
    }
