"""Tests for task-tier-based LLM model routing."""
from __future__ import annotations
import pytest
from app.brain.llm_factory import (
    TaskType, TaskTier, Provider,
    TASK_TIER_MAP, TIER_MODEL_MAP,
    DEFAULT_TASK_SPECS, _resolve_spec,
)

def test_all_task_types_in_tier_map():
    for task in TaskType:
        assert task in TASK_TIER_MAP, f"{task} missing from TASK_TIER_MAP"

def test_tier_map_values_are_valid_tiers():
    for task, tier in TASK_TIER_MAP.items():
        assert isinstance(tier, TaskTier)

def test_tier_model_map_has_all_providers():
    for provider in [Provider.anthropic, Provider.openai, Provider.bedrock, Provider.azure]:
        assert provider in TIER_MODEL_MAP
        for tier in TaskTier:
            assert tier in TIER_MODEL_MAP[provider], f"{provider} missing tier {tier}"

def test_heavy_tasks_use_best_models():
    heavy_tasks = [t for t, tier in TASK_TIER_MAP.items() if tier == TaskTier.HEAVY]
    assert TaskType.exploit_engine in heavy_tasks
    assert TaskType.exploit_script in heavy_tasks
    assert TaskType.execution_judge in heavy_tasks

def test_light_tasks_use_cheap_models():
    light_tasks = [t for t, tier in TASK_TIER_MAP.items() if tier == TaskTier.LIGHT]
    assert TaskType.severity_assessor in light_tasks
    assert TaskType.semantic_modeler in light_tasks

def test_anthropic_heavy_is_opus():
    assert "opus" in TIER_MODEL_MAP[Provider.anthropic][TaskTier.HEAVY].lower()

def test_anthropic_light_is_haiku():
    assert "haiku" in TIER_MODEL_MAP[Provider.anthropic][TaskTier.LIGHT].lower()

@pytest.mark.asyncio
async def test_resolve_spec_no_org_returns_default():
    spec = await _resolve_spec(TaskType.exploit_engine, org_id=None)
    # No org → DEFAULT_TASK_SPECS fallback
    assert spec == DEFAULT_TASK_SPECS[TaskType.exploit_engine]

@pytest.mark.asyncio
async def test_resolve_spec_with_org_no_rows_returns_default(db_session):
    import uuid
    spec = await _resolve_spec(TaskType.exploit_engine, org_id=uuid.uuid4())
    # Org exists but has no OrgLLMTaskConfig or OrgLLMCredential rows → fallback
    assert spec == DEFAULT_TASK_SPECS[TaskType.exploit_engine]

@pytest.mark.asyncio
async def test_resolve_spec_org_with_credential_uses_tier(db_session):
    import uuid
    from app.models.org_llm import OrgLLMCredential
    from app.models.organization import Organization
    from app.database import AsyncSessionLocal

    org = Organization(name=f"tier-test-{uuid.uuid4()}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    # Add an anthropic credential for the org
    cred = OrgLLMCredential(org_id=org.id, provider="anthropic")
    db_session.add(cred)
    await db_session.commit()

    # exploit_engine is HEAVY → should return opus
    spec = await _resolve_spec(TaskType.exploit_engine, org_id=org.id)
    assert "opus" in spec.model.lower()
    assert spec.provider == Provider.anthropic

@pytest.mark.asyncio
async def test_resolve_spec_explicit_task_config_beats_tier(db_session):
    import uuid
    from app.models.org_llm import OrgLLMCredential, OrgLLMTaskConfig
    from app.models.organization import Organization

    org = Organization(name=f"override-test-{uuid.uuid4()}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    cred = OrgLLMCredential(org_id=org.id, provider="anthropic")
    db_session.add(cred)

    # Explicit override: use haiku for exploit_engine (normally HEAVY → opus)
    config = OrgLLMTaskConfig(
        org_id=org.id,
        task_type="exploit_engine",
        provider="anthropic",
        model="claude-haiku-4-5",
        max_tokens=4000,
    )
    db_session.add(config)
    await db_session.commit()

    spec = await _resolve_spec(TaskType.exploit_engine, org_id=org.id)
    assert spec.model == "claude-haiku-4-5"
