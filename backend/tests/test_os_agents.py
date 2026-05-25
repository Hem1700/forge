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
