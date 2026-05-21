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

