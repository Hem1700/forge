# backend/tests/test_validator.py
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.validator.challenger import Challenger
from app.validator.context import ContextChecker
from app.validator.severity import SeverityAssessor
from app.validator.scorer import ConfidenceScorer


def make_finding():
    return {
        "id": str(uuid.uuid4()),
        "engagement_id": str(uuid.uuid4()),
        "title": "IDOR in /api/users/{id}",
        "vulnerability_class": "idor",
        "affected_surface": "https://example.com/api/users/2",
        "description": "Accessing /api/users/2 while authenticated as user 1 returns user 2 data",
        "reproduction_steps": [
            "Login as user1",
            "GET /api/users/2",
            "Response contains user2 PII"
        ],
        "evidence": [{"type": "http_trace", "request": "GET /api/users/2", "response_status": 200}],
        "severity": "high",
        "cvss_score": 7.5,
    }


@pytest.mark.asyncio
async def test_challenger_reproduces_finding():
    challenger = Challenger()
    finding = make_finding()
    mock_response = MagicMock()
    mock_response.content = '{"reproduced": true, "confidence": 0.88, "notes": "Confirmed IDOR - user 2 data returned without authorization"}'
    with patch.object(challenger._llm, "ainvoke", return_value=mock_response):
        result = await challenger.challenge(finding)
    assert result["reproduced"] is True
    assert result["confidence"] >= 0.8


@pytest.mark.asyncio
async def test_context_checker_passes_in_scope():
    checker = ContextChecker()
    finding = make_finding()
    scope = ["example.com", "api.example.com"]
    result = await checker.check(finding, scope=scope, out_of_scope=[])
    assert result["in_scope"] is True
    assert result["is_known_false_positive"] is False


@pytest.mark.asyncio
async def test_context_checker_rejects_out_of_scope():
    checker = ContextChecker()
    finding = make_finding()
    result = await checker.check(finding, scope=["other.com"], out_of_scope=[])
    assert result["in_scope"] is False


@pytest.mark.asyncio
async def test_severity_assessor_returns_cvss():
    assessor = SeverityAssessor()
    finding = make_finding()
    semantic_model = {"app_type": "saas", "user_roles": ["user", "admin"]}
    mock_response = MagicMock()
    mock_response.content = '{"severity": "high", "cvss_score": 7.5, "business_impact": "Cross-user data exposure", "justification": "IDOR allows horizontal privilege escalation"}'
    with patch.object(assessor._llm, "ainvoke", return_value=mock_response):
        result = await assessor.assess(finding, semantic_model)
    assert result["severity"] == "high"
    assert result["cvss_score"] == 7.5


def test_scorer_passes_high_confidence():
    scorer = ConfidenceScorer(threshold=0.75)
    result = scorer.score(
        challenger_result={"reproduced": True, "confidence": 0.88},
        context_result={"in_scope": True, "is_known_false_positive": False},
        severity_result={"severity": "high", "cvss_score": 7.5},
    )
    assert result["final_score"] >= 0.75
    assert result["passes_gate"] is True


def test_scorer_fails_low_confidence():
    scorer = ConfidenceScorer(threshold=0.75)
    result = scorer.score(
        challenger_result={"reproduced": False, "confidence": 0.3},
        context_result={"in_scope": True, "is_known_false_positive": False},
        severity_result={"severity": "low", "cvss_score": 2.0},
    )
    assert result["passes_gate"] is False
