# backend/tests/test_brain.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.brain.semantic_modeler import SemanticModeler


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
