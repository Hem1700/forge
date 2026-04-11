# backend/tests/test_brain.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.brain.semantic_modeler import SemanticModeler
from app.brain.campaign_planner import CampaignPlanner
from app.brain.evasion_strategist import EvasionStrategist
from app.brain.memory_engine import MemoryEngine


@pytest.mark.asyncio
async def test_semantic_modeler_returns_model():
    modeler = SemanticModeler()
    mock_response = MagicMock()
    mock_response.content = '''
    {
        "app_type": "saas",
        "tech_stack": ["nodejs", "react", "postgresql"],
        "endpoints": ["/api/auth/login", "/api/users", "/api/projects"],
        "user_roles": ["admin", "member", "viewer"],
        "business_flows": ["user_registration", "project_creation", "billing"],
        "trust_boundaries": ["unauthenticated", "authenticated", "admin_only"],
        "interesting_surfaces": ["/api/auth/login", "/api/users/{id}"]
    }
    '''
    with patch.object(modeler._llm, "ainvoke", return_value=mock_response):
        model = await modeler.build(
            target_url="https://example.com",
            crawl_data={"paths": ["/api/auth/login", "/api/users"], "headers": {"server": "nginx"}},
        )
    assert model["app_type"] == "saas"
    assert "nodejs" in model["tech_stack"]
    assert len(model["endpoints"]) > 0


@pytest.mark.asyncio
async def test_semantic_modeler_crawl():
    modeler = SemanticModeler()
    crawl_data = await modeler.crawl("https://httpbin.org")
    assert "paths" in crawl_data
    assert "headers" in crawl_data


@pytest.mark.asyncio
async def test_campaign_planner_returns_hypotheses():
    planner = CampaignPlanner()
    semantic_model = {
        "app_type": "fintech",
        "tech_stack": ["nodejs", "postgresql"],
        "endpoints": ["/api/auth/login", "/api/transfer", "/api/balance"],
        "user_roles": ["user", "admin"],
        "business_flows": ["login", "fund_transfer", "balance_check"],
        "trust_boundaries": ["unauthenticated", "authenticated"],
        "interesting_surfaces": ["/api/transfer", "/api/auth/login"],
    }
    mock_response = MagicMock()
    mock_response.content = '''[
        {
            "title": "Race condition in /api/transfer",
            "surface": "/api/transfer",
            "attack_class": "race_condition",
            "reasoning": "Fund transfer flows in fintech apps commonly have TOCTOU vulnerabilities",
            "confidence": 0.82,
            "priority": "critical"
        },
        {
            "title": "IDOR in balance endpoint",
            "surface": "/api/balance",
            "attack_class": "idor",
            "reasoning": "Balance endpoints often lack proper authorization checks",
            "confidence": 0.71,
            "priority": "high"
        }
    ]'''
    with patch.object(planner._llm, "ainvoke", return_value=mock_response):
        hypotheses = await planner.generate(semantic_model=semantic_model, kb_context=[])
    assert len(hypotheses) == 2
    assert hypotheses[0]["attack_class"] == "race_condition"
    assert hypotheses[0]["confidence"] == 0.82


@pytest.mark.asyncio
async def test_evasion_strategist_returns_guidelines():
    strategist = EvasionStrategist()
    mock_response = MagicMock()
    mock_response.content = '''{
        "waf_detected": true,
        "waf_type": "cloudflare",
        "rate_limit_detected": true,
        "rate_limit_rps": 10,
        "guidelines": [
            "Use chunked encoding to bypass WAF body inspection",
            "Space requests at least 200ms apart",
            "Rotate User-Agent headers"
        ],
        "stealth_level": "quiet"
    }'''
    with patch.object(strategist._llm, "ainvoke", return_value=mock_response):
        guidelines = await strategist.analyze(
            target_url="https://example.com",
            headers={"server": "cloudflare", "cf-ray": "abc123"},
            response_codes=[200, 429, 403],
        )
    assert guidelines["waf_detected"] is True
    assert len(guidelines["guidelines"]) > 0


@pytest.mark.asyncio
async def test_memory_engine_write(tmp_path):
    engine = MemoryEngine()
    findings = [
        {
            "title": "IDOR in /api/users",
            "vulnerability_class": "idor",
            "affected_surface": "/api/users/{id}",
            "severity": "high",
            "confidence_score": 0.91,
        }
    ]
    semantic_model = {
        "app_type": "saas",
        "tech_stack": ["nodejs", "postgresql"],
    }
    with patch.object(engine._kb.vector, "upsert", new_callable=AsyncMock) as mock_upsert, \
         patch.object(engine._kb.graph, "upsert_technique", new_callable=AsyncMock):
        await engine.write_back(
            engagement_id="eng-001",
            findings=findings,
            semantic_model=semantic_model,
            failed_hypotheses=[],
        )
        assert mock_upsert.called
