# cli/tests/test_org_llm_cli.py
"""Smoke tests for forge org llm CLI commands."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from forge_cli.main import cli


def _client_returning(data):
    mock = MagicMock()
    mock._request.return_value = data
    return mock


# ── forge org llm show ────────────────────────────────────────────────────────

def test_llm_show_renders_table():
    creds = [
        {"provider": "anthropic", "configured": True, "use_iam_role": False, "last_tested_at": None, "region": None, "endpoint": None},
        {"provider": "openai", "configured": False},
        {"provider": "bedrock", "configured": True, "use_iam_role": True, "region": "us-east-1", "last_tested_at": None, "endpoint": None},
        {"provider": "azure", "configured": False},
    ]
    task_cfg = {
        "preset": "balanced",
        "tasks": {
            "findings_judge": {"provider": "anthropic", "model": "claude-sonnet-4-6", "from_default": True},
        },
    }

    mock_client = MagicMock()
    mock_client._request.side_effect = [creds, task_cfg]

    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "show"])

    assert result.exit_code == 0
    assert "anthropic" in result.output
    assert "balanced" in result.output
    assert "findings_judge" in result.output


# ── forge org llm preset ──────────────────────────────────────────────────────

def test_llm_preset_smart():
    mock_client = _client_returning({"preset": "smart", "tasks_configured": 14})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "preset", "smart"])
    assert result.exit_code == 0
    assert "smart" in result.output
    mock_client._request.assert_called_once_with(
        "PUT", "/api/v1/org/llm/task-config", body={"preset": "smart"}
    )


def test_llm_preset_balanced():
    mock_client = _client_returning({"preset": "balanced", "tasks_configured": 0})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "preset", "balanced"])
    assert result.exit_code == 0


def test_llm_preset_invalid_rejected():
    runner = CliRunner()
    result = runner.invoke(cli, ["org", "llm", "preset", "ultra"])
    assert result.exit_code != 0


# ── forge org llm set ─────────────────────────────────────────────────────────

def test_llm_set_task():
    mock_client = _client_returning({"preset": "custom", "tasks_configured": 1})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, [
            "org", "llm", "set", "findings_judge",
            "--provider", "openai", "--model", "gpt-4-turbo",
        ])
    assert result.exit_code == 0
    assert "findings_judge" in result.output
    mock_client._request.assert_called_once_with(
        "PUT", "/api/v1/org/llm/task-config",
        body={"custom": {"findings_judge": {"provider": "openai", "model": "gpt-4-turbo"}}},
    )


# ── forge org llm key set ─────────────────────────────────────────────────────

def test_key_set_anthropic():
    mock_client = _client_returning({"provider": "anthropic", "configured": True})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "key", "set", "anthropic"],
                               input="sk-ant-fake-key\n")
    assert result.exit_code == 0
    assert "saved" in result.output.lower()
    called_body = mock_client._request.call_args[1]["body"]
    assert called_body["api_key"] == "sk-ant-fake-key"
    assert called_body["use_iam_role"] is False


def test_key_set_bedrock_iam():
    mock_client = _client_returning({"provider": "bedrock", "configured": True})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, [
            "org", "llm", "key", "set", "bedrock",
            "--iam-role", "--region", "eu-west-1",
        ])
    assert result.exit_code == 0
    called_body = mock_client._request.call_args[1]["body"]
    assert called_body["use_iam_role"] is True
    assert called_body["region"] == "eu-west-1"


# ── forge org llm key test ────────────────────────────────────────────────────

def test_key_test_ok():
    mock_client = _client_returning({"ok": True})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "key", "test", "anthropic"])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_key_test_failure_exits_nonzero():
    mock_client = _client_returning({"ok": False, "error": "invalid api key"})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "key", "test", "anthropic"])
    assert result.exit_code == 1
    assert "invalid api key" in result.output


# ── forge org llm key revoke ──────────────────────────────────────────────────

def test_key_revoke_with_yes():
    mock_client = _client_returning({"provider": "openai", "revoked": True})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "key", "revoke", "openai", "--yes"])
    assert result.exit_code == 0
    assert "revoked" in result.output.lower()
    mock_client._request.assert_called_once_with("DELETE", "/api/v1/org/llm/credentials/openai")


# ── forge org llm usage ───────────────────────────────────────────────────────

def test_usage_renders_table():
    mock_client = _client_returning({
        "total_cost_usd": 0.0042,
        "rows": [
            {"task": "findings_judge", "provider": "anthropic", "model": "claude-sonnet-4-6",
             "calls": 5, "input_tokens": 1200, "output_tokens": 300, "cost_usd": 0.0042},
        ],
    })
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "usage"])
    assert result.exit_code == 0
    # Rich may truncate long task names; check a prefix and the cost
    assert "findings_" in result.output
    assert "0.0042" in result.output


def test_usage_empty():
    mock_client = _client_returning({"total_cost_usd": 0.0, "rows": []})
    runner = CliRunner()
    with patch("forge_cli.commands.org_llm._make_client", return_value=mock_client):
        result = runner.invoke(cli, ["org", "llm", "usage"])
    assert result.exit_code == 0
    assert "No usage" in result.output
