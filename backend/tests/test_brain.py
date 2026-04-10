# backend/tests/test_brain.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.brain.semantic_modeler import SemanticModeler
from app.brain.campaign_planner import CampaignPlanner


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
