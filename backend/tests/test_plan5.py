"""Tests for Plan 5: multi-target support (codebase modeler, new agents, /start endpoint)."""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from app.brain.codebase_modeler import CodebaseModeler
from app.swarm.agents.code_analyzer import CodeAnalyzerAgent
from app.swarm.agents.dependency_scanner import DependencyScannerAgent
from app.swarm.agents.fuzzer import FuzzerAgent, PAYLOADS


RAVEN_PATH = "/Users/hemparekh/Desktop/raven"


def test_codebase_modeler_profile():
    """Profile should walk the target path and return the documented shape."""
    if not Path(RAVEN_PATH).exists():
        pytest.skip(f"Raven test target not available at {RAVEN_PATH}")

    with patch("app.brain.codebase_modeler.ChatAnthropic"):
        modeler = CodebaseModeler()

    profile = modeler.profile(RAVEN_PATH)

    assert set(profile.keys()) == {"root", "structure", "files"}
    assert profile["root"] == RAVEN_PATH
    assert isinstance(profile["structure"], list)
    assert isinstance(profile["files"], list)
    # Profile caps
    assert len(profile["structure"]) <= 200
    assert len(profile["files"]) <= CodebaseModeler.MAX_FILES
    # Each file entry has the expected keys
    for f in profile["files"]:
        assert {"path", "content", "priority"} <= set(f.keys())
        assert len(f["content"]) <= CodebaseModeler.MAX_FILE_CHARS


def test_codebase_modeler_skips_venv(tmp_path):
    """Skip dirs listed in SKIP_DIRS should be pruned during walk."""
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("secret = 1")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "keep.py").write_text("import os")

    with patch("app.brain.codebase_modeler.ChatAnthropic"):
        modeler = CodebaseModeler()

    profile = modeler.profile(str(tmp_path))
    paths = [f["path"] for f in profile["files"]]
    assert any("keep.py" in p for p in paths)
    assert not any(".venv" in p for p in paths)


def test_dependency_scanner_parse_pypi(tmp_path):
    """_parse_deps should extract name/version from requirements.txt."""
    req = tmp_path / "requirements.txt"
    req.write_text(
        "# comment line\n"
        "requests==2.28.0\n"
        "flask>=2.0\n"
        "urllib3\n"
        "django~=4.2.1\n"
        "\n"
    )

    scanner = DependencyScannerAgent(
        agent_id="a1", engagement_id="e1", agent_type="dependency_scanner", tools=[]
    )
    pkgs = scanner._parse_deps(req, "PyPI")

    names = {p["name"] for p in pkgs}
    assert {"requests", "flask", "urllib3", "django"} <= names
    by_name = {p["name"]: p for p in pkgs}
    assert by_name["requests"]["version"] == "2.28.0"
    assert by_name["flask"]["version"] == "2.0"
    assert by_name["urllib3"]["version"] is None


def test_dependency_scanner_parse_npm(tmp_path):
    """npm parsing should read dependencies + devDependencies, stripping leading ^ ~."""
    pkg = tmp_path / "package.json"
    pkg.write_text(
        '{"dependencies": {"lodash": "^4.17.21"}, '
        '"devDependencies": {"jest": "~29.0.0"}}'
    )
    scanner = DependencyScannerAgent(
        agent_id="a1", engagement_id="e1", agent_type="dependency_scanner", tools=[]
    )
    pkgs = scanner._parse_deps(pkg, "npm")
    by_name = {p["name"]: p for p in pkgs}
    assert by_name["lodash"]["version"] == "4.17.21"
    assert by_name["jest"]["version"] == "29.0.0"


def test_dependency_scanner_osv_severity():
    """OSV severity score mapping should bucket CVSS correctly."""
    scanner = DependencyScannerAgent(
        agent_id="a1", engagement_id="e1", agent_type="dependency_scanner", tools=[]
    )
    assert scanner._osv_severity({"severity": [{"score": "9.5"}]}) == "critical"
    assert scanner._osv_severity({"severity": [{"score": "7.2"}]}) == "high"
    assert scanner._osv_severity({"severity": [{"score": "5.0"}]}) == "medium"
    assert scanner._osv_severity({"severity": [{"score": "2.1"}]}) == "low"
    assert scanner._osv_severity({}) == "medium"


def test_fuzzer_payloads_defined():
    """Every canonical surface type must have at least one payload."""
    required = {"path_traversal", "cli_arg", "env_var", "file_input", "config"}
    assert required <= PAYLOADS.keys()
    for surface_type, payloads in PAYLOADS.items():
        assert len(payloads) > 0, f"No payloads for {surface_type}"


def test_code_analyzer_agent_defaults():
    """CodeAnalyzerAgent should initialize with correct BaseAgent fields and an LLM wrapper."""
    with patch("app.swarm.agents.code_analyzer.ChatAnthropic"):
        agent = CodeAnalyzerAgent(
            agent_id="agent-xyz",
            engagement_id="eng-abc",
            agent_type="code_analyzer",
            tools=["llm_review"],
        )
    assert agent.agent_id == "agent-xyz"
    assert agent.engagement_id == "eng-abc"
    assert agent.agent_type == "code_analyzer"
    assert agent.tools == ["llm_review"]
    assert agent._llm is not None


def test_fuzzer_agent_defaults():
    """FuzzerAgent should be instantiable via BaseAgent dataclass interface."""
    agent = FuzzerAgent(
        agent_id="f1", engagement_id="e1", agent_type="fuzzer", tools=["subprocess"]
    )
    assert agent.agent_type == "fuzzer"
    assert agent.tools == ["subprocess"]


@pytest.mark.asyncio
async def test_start_endpoint_not_found(http_client):
    """POST /start on a missing engagement id returns 404."""
    missing_id = uuid.uuid4()
    response = await http_client.post(f"/api/v1/engagements/{missing_id}/start")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_start_endpoint_local_codebase(http_client):
    """POST /start on a local_codebase engagement returns 202 and dispatches the codebase pipeline."""
    create_resp = await http_client.post(
        "/api/v1/engagements/",
        json={
            "target_url": "local://raven",
            "target_type": "local_codebase",
            "target_path": RAVEN_PATH,
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["target_type"] == "local_codebase"
    assert body["target_path"] == RAVEN_PATH
    engagement_id = body["id"]

    # Mock the background pipeline so we don't actually hit Anthropic / subprocess
    with patch(
        "app.api.start._run_codebase_pipeline", new=AsyncMock(return_value=None)
    ) as mock_pipeline:
        response = await http_client.post(
            f"/api/v1/engagements/{engagement_id}/start"
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "started"
    assert payload["target_type"] == "local_codebase"
    assert payload["engagement_id"] == engagement_id
    # BackgroundTasks runs the task after response is returned; inside
    # httpx/ASGITransport this happens synchronously before the client
    # yields the response object.
    mock_pipeline.assert_called_once()


@pytest.mark.asyncio
async def test_start_endpoint_web_default(http_client):
    """Web engagements (default target_type) should route to the web pipeline."""
    create_resp = await http_client.post(
        "/api/v1/engagements/",
        json={"target_url": "https://example.com"},
    )
    assert create_resp.status_code == 201
    engagement_id = create_resp.json()["id"]
    assert create_resp.json()["target_type"] == "web"

    with patch(
        "app.api.start._run_web_pipeline", new=AsyncMock(return_value=None)
    ) as mock_pipeline:
        response = await http_client.post(
            f"/api/v1/engagements/{engagement_id}/start"
        )

    assert response.status_code == 202
    assert response.json()["target_type"] == "web"
    mock_pipeline.assert_called_once()
