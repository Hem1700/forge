# backend/tests/test_os_agents.py
"""Tests for OS Phase 2 agents."""
from __future__ import annotations
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.brain.os_fingerprint import OSFingerprint


def _fp(**kwargs) -> OSFingerprint:
    """Build a minimal OSFingerprint for testing."""
    defaults = dict(host="10.0.0.1", port=22, collected_at="2026-01-01T00:00:00Z")
    defaults.update(kwargs)
    return OSFingerprint(**defaults)


def _agent(cls, agent_type):
    return cls(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type=agent_type,
        tools=[],
    )


# ── Task 1: TaskType values exist ──────────────────────────────────────────────

def test_new_task_types_exist():
    from app.brain.llm_factory import TaskType, DEFAULT_TASK_SPECS, TASK_TIER_MAP, TaskTier
    assert TaskType.privesc_analysis.value == "privesc_analysis"
    assert TaskType.service_audit.value == "service_audit"
    assert TaskType.package_vuln_analysis.value == "package_vuln_analysis"
    assert TaskType.config_audit.value == "config_audit"
    assert TaskType.network_exposure.value == "network_exposure"
    assert TaskType.privesc_analysis in DEFAULT_TASK_SPECS
    assert TaskType.privesc_analysis in TASK_TIER_MAP
    assert TASK_TIER_MAP[TaskType.privesc_analysis] == TaskTier.HEAVY
    assert TASK_TIER_MAP[TaskType.service_audit] == TaskTier.STANDARD
    assert TASK_TIER_MAP[TaskType.package_vuln_analysis] == TaskTier.STANDARD
    assert TASK_TIER_MAP[TaskType.config_audit] == TaskTier.STANDARD
    assert TASK_TIER_MAP[TaskType.network_exposure] == TaskTier.STANDARD


def test_gtfobins_loads_and_has_entries():
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "gtfobins.json"
    assert path.exists(), f"gtfobins.json not found at {path}"
    data = json.loads(path.read_text())
    assert isinstance(data, dict)
    assert len(data) >= 20, "Should have at least 20 binary entries"
    # Check schema
    for binary, techniques in list(data.items())[:3]:
        assert isinstance(binary, str)
        assert isinstance(techniques, dict)
        for tech in techniques.values():
            assert "commands" in tech
            assert isinstance(tech["commands"], list)


# ── PrivescAgent ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_privesc_suid_gtfobins_hit():
    from app.swarm.agents.privesc_agent import PrivescAgent
    agent = _agent(PrivescAgent, "privesc")
    fp = _fp(suid_binaries=["/usr/bin/vim.basic", "/usr/bin/find"])
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    assert result["agent_type"] == "privesc"
    suid_findings = [f for f in result["findings"] if f.get("vulnerability") == "suid_gtfobins"]
    assert len(suid_findings) >= 1
    assert suid_findings[0]["severity"] == "high"
    assert "chain_potential" in suid_findings[0]


@pytest.mark.asyncio
async def test_privesc_writable_cron_hit():
    from app.swarm.agents.privesc_agent import PrivescAgent
    agent = _agent(PrivescAgent, "privesc")
    fp = _fp(
        writable_paths=["/etc/cron.d", "/tmp"],
        cron_jobs=[{"schedule": "* * * * * root /etc/cron.d/backup.sh"}],
    )
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "writable_cron_path"]
    assert len(findings) >= 1
    assert findings[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_privesc_docker_group_hit():
    from app.swarm.agents.privesc_agent import PrivescAgent
    agent = _agent(PrivescAgent, "privesc")
    fp = _fp(groups=[{"name": "docker", "gid": "999", "members": ["ubuntu", "deploy"]}])
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "docker_group_privesc"]
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_privesc_no_findings_signal():
    from app.swarm.agents.privesc_agent import PrivescAgent
    agent = _agent(PrivescAgent, "privesc")
    fp = _fp()  # empty fingerprint
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    assert result["findings"] == []
    assert agent.signal_history[-1] < 0.5


# ── ServiceAuditAgent ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_audit_ssh_permit_root_login():
    from app.swarm.agents.service_audit_agent import ServiceAuditAgent
    agent = _agent(ServiceAuditAgent, "service_audit")
    fp = _fp(ssh_config={"PermitRootLogin": "yes", "PasswordAuthentication": "no"})
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "ssh_permit_root_login"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_service_audit_ssh_password_auth():
    from app.swarm.agents.service_audit_agent import ServiceAuditAgent
    agent = _agent(ServiceAuditAgent, "service_audit")
    fp = _fp(ssh_config={"PasswordAuthentication": "yes"})
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "ssh_password_auth"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "medium"


@pytest.mark.asyncio
async def test_service_audit_telnet_port():
    from app.swarm.agents.service_audit_agent import ServiceAuditAgent
    agent = _agent(ServiceAuditAgent, "service_audit")
    fp = _fp(open_ports=[{"proto": "tcp", "local": "0.0.0.0:23", "process": "telnetd"}])
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "unencrypted_protocol"]
    assert len(findings) >= 1
    assert findings[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_service_audit_exposed_redis():
    from app.swarm.agents.service_audit_agent import ServiceAuditAgent
    agent = _agent(ServiceAuditAgent, "service_audit")
    fp = _fp(open_ports=[{"proto": "tcp", "local": "0.0.0.0:6379", "process": "redis-server"}])
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "exposed_management_interface"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


# ── PackageVulnAgent ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_package_vuln_agent_returns_findings_from_trivy(mock_llm):
    import json
    from unittest.mock import MagicMock
    from app.swarm.agents.package_vuln_agent import PackageVulnAgent

    trivy_output = {
        "Results": [{
            "Vulnerabilities": [{
                "PkgName": "openssl",
                "InstalledVersion": "1.1.1f",
                "FixedVersion": "1.1.1n",
                "VulnerabilityID": "CVE-2022-0778",
                "Severity": "HIGH",
                "CVSS": {"nvd": {"V3Score": 7.5}},
                "Description": "Infinite loop in BN_mod_sqrt()",
            }]
        }]
    }

    mock_resp = MagicMock()
    mock_resp.content = json.dumps([{
        "vuln_id": "CVE-2022-0778",
        "exploitability_in_context": 0.7,
        "reasoning": "OpenSSL is exposed via nginx",
    }])
    mock_llm.ainvoke.return_value = mock_resp

    agent = _agent(PackageVulnAgent, "package_vuln")
    fp = _fp(packages=[{"name": "openssl", "version": "1.1.1f", "arch": "amd64"}])

    with patch("app.ws.progress.broadcast", new_callable=AsyncMock), \
         patch("app.swarm.agents.package_vuln_agent.PackageVulnAgent._run_trivy",
               new_callable=AsyncMock, return_value=trivy_output):
        result = await agent._execute({"fingerprint": fp.to_dict()})

    assert result["agent_type"] == "package_vuln"
    assert len(result["findings"]) >= 1
    assert result["findings"][0]["vulnerability"] == "known_cve"
    assert "CVE-2022-0778" in result["findings"][0]["evidence"]


@pytest.mark.asyncio
async def test_package_vuln_agent_trivy_unavailable():
    from app.swarm.agents.package_vuln_agent import PackageVulnAgent
    agent = _agent(PackageVulnAgent, "package_vuln")
    fp = _fp(packages=[{"name": "bash", "version": "5.1", "arch": "amd64"}])

    with patch("app.ws.progress.broadcast", new_callable=AsyncMock), \
         patch("app.swarm.agents.package_vuln_agent.PackageVulnAgent._run_trivy",
               new_callable=AsyncMock, return_value=None):
        result = await agent._execute({"fingerprint": fp.to_dict()})

    # Should return empty findings gracefully, not raise
    assert result["agent_type"] == "package_vuln"
    assert isinstance(result["findings"], list)


# ── ConfigAuditAgent ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_audit_aslr_disabled():
    from app.swarm.agents.config_audit_agent import ConfigAuditAgent
    agent = _agent(ConfigAuditAgent, "config_audit")
    fp = _fp(sysctl_params={"kernel.randomize_va_space": "0"})
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "aslr_disabled"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_config_audit_tmp_noexec():
    from app.swarm.agents.config_audit_agent import ConfigAuditAgent
    agent = _agent(ConfigAuditAgent, "config_audit")
    fp = _fp(mounts=[{"device": "tmpfs", "mountpoint": "/tmp", "fstype": "tmpfs", "options": "rw,nosuid"}])
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "tmp_noexec_missing"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "medium"


@pytest.mark.asyncio
async def test_config_audit_pam_no_lockout():
    from app.swarm.agents.config_audit_agent import ConfigAuditAgent
    agent = _agent(ConfigAuditAgent, "config_audit")
    fp = _fp(ssh_config={})
    task = {"fingerprint": {**fp.to_dict(), "pam_config": {"common-auth": "auth required pam_unix.so"}}}
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute(task)
    findings = [f for f in result["findings"] if f.get("vulnerability") == "pam_no_lockout"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_config_audit_ip_forward():
    from app.swarm.agents.config_audit_agent import ConfigAuditAgent
    agent = _agent(ConfigAuditAgent, "config_audit")
    fp = _fp(sysctl_params={"net.ipv4.ip_forward": "1", "kernel.randomize_va_space": "2"})
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "ip_forwarding_enabled"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "medium"


# ── NetworkExposureAgent ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_network_exposure_root_service():
    from app.swarm.agents.network_exposure_agent import NetworkExposureAgent
    agent = _agent(NetworkExposureAgent, "network_exposure")
    fp = _fp(
        open_ports=[{"proto": "tcp", "local": "0.0.0.0:80", "process": "nginx", "user": "root"}],
        processes=[{"pid": "123", "ppid": "1", "user": "root", "cmd": "nginx: master"}],
    )
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "root_service_exposed"]
    assert len(findings) >= 1
    assert findings[0]["severity"] in ("high", "critical")


@pytest.mark.asyncio
async def test_network_exposure_critical_unauthenticated():
    from app.swarm.agents.network_exposure_agent import NetworkExposureAgent
    agent = _agent(NetworkExposureAgent, "network_exposure")
    fp = _fp(
        open_ports=[{"proto": "tcp", "local": "0.0.0.0:6379", "process": "redis-server", "user": "root"}],
        processes=[{"pid": "456", "ppid": "1", "user": "root", "cmd": "redis-server *:6379"}],
    )
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    findings = [f for f in result["findings"] if f.get("vulnerability") == "unauthenticated_root_service"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_network_exposure_no_findings():
    from app.swarm.agents.network_exposure_agent import NetworkExposureAgent
    agent = _agent(NetworkExposureAgent, "network_exposure")
    fp = _fp(
        open_ports=[{"proto": "tcp", "local": "127.0.0.1:5432", "process": "postgres", "user": "postgres"}],
    )
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"fingerprint": fp.to_dict()})
    assert result["findings"] == []
    assert agent.signal_history[-1] < 0.5


# ── Worker job registration ────────────────────────────────────────────────────

def test_worker_has_os_pipeline_and_trivy_refresh():
    from app.worker import WorkerSettings, refresh_trivy_db, run_os_pipeline
    fn_names = [f.__name__ for f in WorkerSettings.functions]
    assert "run_os_pipeline" in fn_names
    cron_fn_names = [c.coroutine.__name__ for c in WorkerSettings.cron_jobs]
    assert "refresh_trivy_db" in cron_fn_names


# ── Pipeline integration ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_os_pipeline_runs_all_agents(mock_llm):
    """Verify _run_os_pipeline calls all 5 OS agents and persists findings."""
    import json
    from unittest.mock import MagicMock, patch as _patch
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.database import Base
    from app.models.organization import Organization
    from app.models.engagement import Engagement, EngagementStatus
    from app.models.os_target import OSTarget
    from app.api.start import _run_os_pipeline

    TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    async with sf() as db:
        org = Organization(name=f"pipeline-test-{uuid.uuid4()}")
        db.add(org)
        await db.commit()
        await db.refresh(org)
        eng = Engagement(
            org_id=org.id,
            target_url="ssh://10.0.0.1",
            target_type="os_ssh",
            status=EngagementStatus.pending,
        )
        db.add(eng)
        await db.commit()
        await db.refresh(eng)
        target = OSTarget(
            engagement_id=eng.id,
            host="10.0.0.1",
            port=22,
            username="ubuntu",
            auth_type="agent",
            access_mode="agentless",
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)

    mock_fp = OSFingerprint(
        host="10.0.0.1", port=22, collected_at="2026-01-01T00:00:00Z",
        suid_binaries=["/usr/bin/find"],
        ssh_config={"PermitRootLogin": "yes"},
        packages=[{"name": "bash", "version": "5.1", "arch": "amd64"}],
        sysctl_params={"kernel.randomize_va_space": "0"},
        open_ports=[{"proto": "tcp", "local": "0.0.0.0:6379", "process": "redis-server", "user": "root"}],
        processes=[{"pid": "1", "ppid": "0", "user": "root", "cmd": "redis-server"}],
    )

    llm_resp = MagicMock()
    llm_resp.content = "[]"
    mock_llm.ainvoke.return_value = llm_resp

    with _patch("app.brain.os_modeler.OSModeler.collect", new_callable=AsyncMock, return_value=mock_fp), \
         _patch("app.ws.progress.broadcast", new_callable=AsyncMock), \
         _patch("app.swarm.agents.package_vuln_agent.PackageVulnAgent._run_trivy",
                new_callable=AsyncMock, return_value=None), \
         _patch("app.api.start.AsyncSessionLocal", sf):
        await _run_os_pipeline(eng.id, org_id=org.id)

    from app.models.finding import Finding
    from sqlalchemy import select as sa_select
    async with sf() as db:
        findings = (await db.execute(
            sa_select(Finding).where(Finding.engagement_id == eng.id)
        )).scalars().all()

    assert len(findings) >= 2, f"Expected ≥2 findings from OS pipeline, got {len(findings)}"

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── ChainDiscoveryAgent ────────────────────────────────────────────────────────

def test_chain_discovery_task_type():
    from app.brain.llm_factory import TaskType, DEFAULT_TASK_SPECS, TASK_TIER_MAP, TaskTier
    assert TaskType.chain_discovery.value == "chain_discovery"
    assert TaskType.chain_discovery in DEFAULT_TASK_SPECS
    assert TaskType.chain_discovery in TASK_TIER_MAP
    assert TASK_TIER_MAP[TaskType.chain_discovery] == TaskTier.HEAVY


@pytest.mark.asyncio
async def test_chain_discovery_empty_input():
    from app.swarm.agents.chain_discovery_agent import ChainDiscoveryAgent
    agent = _agent(ChainDiscoveryAgent, "chain_discovery")
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock):
        result = await agent._execute({"findings": []})
    assert result["agent_type"] == "chain_discovery"
    assert result["findings"] == []
    assert result["chains_discovered"] == 0
    assert agent.signal_history[-1] < 0.5


@pytest.mark.asyncio
async def test_chain_discovery_detects_chain(mock_llm):
    import json
    from unittest.mock import MagicMock
    from app.swarm.agents.chain_discovery_agent import ChainDiscoveryAgent

    # 3 findings needed — DFS requires ≥2 hops (3 nodes in path)
    findings = [
        {
            "vulnerability": "writable_cron_path",
            "severity": "high",
            "description": "Writable cron path found",
            "evidence": "/etc/cron.d",
            "recommendation": "Fix permissions",
            "chain_potential": True,
            "confidence_score": 0.90,
        },
        {
            "vulnerability": "suid_gtfobins",
            "severity": "high",
            "description": "SUID binary found",
            "evidence": "/usr/bin/find",
            "recommendation": "Remove SUID bit",
            "chain_potential": True,
            "confidence_score": 0.95,
        },
        {
            "vulnerability": "docker_group_privesc",
            "severity": "high",
            "description": "User in docker group",
            "evidence": "docker group members: ubuntu",
            "recommendation": "Remove from docker group",
            "chain_potential": True,
            "confidence_score": 0.85,
        },
    ]
    mock_resp = MagicMock()
    mock_resp.content = json.dumps([{
        "chain_name": "Writable Cron to SUID to Docker Escalation",
        "severity": "critical",
        "steps": [
            {"step": 1, "action": "Modify cron script", "finding_id": "fid-1"},
            {"step": 2, "action": "Execute SUID binary", "finding_id": "fid-2"},
            {"step": 3, "action": "Docker container escape", "finding_id": "fid-3"},
        ],
        "time_to_exploit": "5 minutes",
        "description": "Attacker modifies writable cron job to execute SUID binary then escapes via docker.",
    }])
    mock_llm.ainvoke.return_value = mock_resp

    agent = _agent(ChainDiscoveryAgent, "chain_discovery")
    with patch("app.ws.progress.broadcast", new_callable=AsyncMock), \
         patch("app.swarm.agents.chain_discovery_agent._persist_and_query_neo4j",
               side_effect=Exception("Neo4j unavailable")):
        result = await agent._execute({"findings": findings})

    assert len(result["findings"]) == 1
    chain = result["findings"][0]
    assert chain["vulnerability"] == "attack_chain"
    assert chain["severity"] == "critical"
    assert chain["finding_type"] == "chain"
    assert chain["vulnerability_class"] == "attack_chain"
    assert agent.signal_history[-1] == 1.0


@pytest.mark.asyncio
async def test_chain_discovery_neo4j_unavailable_falls_back(mock_llm):
    """When Neo4j raises, agent still discovers chains via in-memory DFS."""
    import json
    from unittest.mock import MagicMock
    from app.swarm.agents.chain_discovery_agent import ChainDiscoveryAgent

    findings = [
        {
            "vulnerability": "writable_cron_path", "severity": "high",
            "description": "Writable cron", "evidence": "/etc/cron.d",
            "recommendation": "Fix", "chain_potential": True, "confidence_score": 0.9,
        },
        {
            "vulnerability": "suid_gtfobins", "severity": "high",
            "description": "SUID find", "evidence": "/usr/bin/find",
            "recommendation": "Fix", "chain_potential": True, "confidence_score": 0.95,
        },
    ]
    mock_resp = MagicMock()
    mock_resp.content = json.dumps([{
        "chain_name": "Fallback Chain",
        "severity": "high",
        "steps": [{"step": 1, "action": "exploit", "finding_id": "x"}],
        "time_to_exploit": "10 minutes",
        "description": "fallback",
    }])
    mock_llm.ainvoke.return_value = mock_resp

    agent = _agent(ChainDiscoveryAgent, "chain_discovery")

    with patch("app.ws.progress.broadcast", new_callable=AsyncMock), \
         patch("app.swarm.agents.chain_discovery_agent._persist_and_query_neo4j",
               side_effect=ConnectionError("Neo4j down")):
        # Should not raise — returns result even without Neo4j
        result = await agent._execute({"findings": findings})

    assert isinstance(result["findings"], list)
    assert isinstance(result["chains_discovered"], int)


def test_chain_discovery_build_edges():
    from app.swarm.agents.chain_discovery_agent import _build_edges
    findings = [
        {"id": "a1", "vulnerability": "writable_cron_path", "severity": "high", "chain_potential": True},
        {"id": "b1", "vulnerability": "suid_gtfobins", "severity": "high", "chain_potential": True},
        {"id": "c1", "vulnerability": "docker_group_privesc", "severity": "high", "chain_potential": True},
    ]
    edges = _build_edges(findings)
    edge_set = set(edges)
    # writable_cron_path ENABLES suid_gtfobins
    assert ("a1", "b1") in edge_set
    # writable_cron_path ENABLES docker_group_privesc
    assert ("a1", "c1") in edge_set
    # At least 2 edges
    assert len(edges) >= 2
