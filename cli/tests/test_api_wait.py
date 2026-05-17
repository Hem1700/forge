"""Unit tests for ForgeClient.wait_for_engagement()."""
import pytest
from unittest.mock import patch
from forge_cli.api import ForgeClient


def _client() -> ForgeClient:
    return ForgeClient("http://localhost:8080", api_key="test-key")


def test_wait_returns_immediately_when_complete():
    client = _client()
    eng = {"id": "abc", "status": "complete"}
    with patch.object(client, "get_engagement", return_value=eng), \
         patch("forge_cli.api.time") as mock_time:
        mock_time.monotonic.return_value = 0
        result = client.wait_for_engagement("abc", timeout=30, poll_interval=1)
    assert result["status"] == "complete"
    mock_time.sleep.assert_not_called()


def test_wait_polls_until_complete():
    client = _client()
    responses = [
        {"id": "abc", "status": "running"},
        {"id": "abc", "status": "running"},
        {"id": "abc", "status": "complete"},
    ]
    with patch.object(client, "get_engagement", side_effect=responses), \
         patch("forge_cli.api.time") as mock_time:
        mock_time.monotonic.return_value = 0
        result = client.wait_for_engagement("abc", timeout=30, poll_interval=5)
    assert result["status"] == "complete"
    assert mock_time.sleep.call_count == 2


def test_wait_raises_timeout():
    client = _client()
    with patch.object(client, "get_engagement", return_value={"id": "abc", "status": "running"}), \
         patch("forge_cli.api.time") as mock_time:
        # deadline = 0 + 30 = 30; first check returns 31 → timeout
        mock_time.monotonic.side_effect = [0, 31]
        with pytest.raises(TimeoutError, match="Timed out"):
            client.wait_for_engagement("abc", timeout=30, poll_interval=1)


def test_wait_returns_aborted_status():
    client = _client()
    eng = {"id": "abc", "status": "aborted"}
    with patch.object(client, "get_engagement", return_value=eng), \
         patch("forge_cli.api.time") as mock_time:
        mock_time.monotonic.return_value = 0
        result = client.wait_for_engagement("abc", timeout=30, poll_interval=1)
    assert result["status"] == "aborted"
