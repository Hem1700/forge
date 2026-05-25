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
