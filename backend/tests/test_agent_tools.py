# backend/tests/test_agent_tools.py
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from app.brain.agent_tools import HttpRequestTool, ExtractPatternTool, SubprocessTool


@pytest.mark.asyncio
async def test_http_request_tool_returns_status_headers_body():
    tool = HttpRequestTool()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html"}
    mock_resp.text = "<html>hello</html>"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch("app.brain.agent_tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute({"method": "GET", "url": "https://target.com"})

    assert "STATUS 200" in result
    assert "content-type" in result
    assert "<html>hello</html>" in result


@pytest.mark.asyncio
async def test_http_request_tool_truncates_body_to_4000():
    tool = HttpRequestTool()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.text = "x" * 5000

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch("app.brain.agent_tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute({"method": "GET", "url": "https://target.com"})

    body_section = result.split("BODY\n", 1)[1]
    assert len(body_section) == 4000


@pytest.mark.asyncio
async def test_extract_pattern_tool_finds_matches():
    tool = ExtractPatternTool()
    result = await tool.execute({
        "pattern": r"\d+",
        "text": "user id: 42, session: 99",
        "mode": "regex",
    })
    assert "42" in result
    assert "99" in result


@pytest.mark.asyncio
async def test_extract_pattern_tool_no_matches():
    tool = ExtractPatternTool()
    result = await tool.execute({"pattern": r"NOMATCH_XYZ", "text": "nothing here"})
    assert result == "no matches found"


@pytest.mark.asyncio
async def test_subprocess_tool_rejects_unknown_tool():
    tool = SubprocessTool()
    result = await tool.execute({"tool": "rm", "args": "-rf /"})
    assert "not an allowed tool" in result


@pytest.mark.asyncio
async def test_subprocess_tool_runs_allowed_tool_in_kali_image():
    tool = SubprocessTool()
    mock_result = {
        "stdout": "curl output\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "executed_at": "2026-04-18T00:00:00+00:00",
    }
    with patch("app.brain.agent_tools.ExploitExecutor") as mock_cls:
        mock_executor = mock_cls.return_value
        mock_executor.execute = AsyncMock(return_value=mock_result)
        result = await tool.execute({"tool": "curl", "args": "https://target.com"})

    assert "EXIT 0" in result
    assert "curl output" in result
    call_kwargs = mock_executor.execute.call_args[1]
    assert call_kwargs.get("image") == "kalilinux/kali-rolling"
    assert call_kwargs.get("timeout") == 120


@pytest.mark.asyncio
async def test_http_request_tool_returns_error_string_on_network_failure():
    tool = HttpRequestTool()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("app.brain.agent_tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute({"method": "GET", "url": "https://unreachable.example"})

    assert "request error" in result
