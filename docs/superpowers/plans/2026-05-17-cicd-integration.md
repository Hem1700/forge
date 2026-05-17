# CI/CD Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `forge ci scan` and `forge ci report` commands that run a FORGE security scan from any CI pipeline, gate on finding severity, and post results to GitHub (commit status + comment) or a generic callback URL.

**Architecture:** All new code lives in the CLI. `ci.py` contains pure functions (formatting, GitHub API calls, threshold logic). `commands/ci.py` contains the Click commands that orchestrate the flow: create engagement → start → poll via new `wait_for_engagement()` → fetch findings → report back → exit 0/1. No backend changes needed.

**Tech Stack:** Click, Rich, Python stdlib `urllib` (already in use), `time` (stdlib)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `cli/tests/__init__.py` | Makes `tests/` a package for pytest |
| Create | `cli/tests/test_ci.py` | Unit tests for `ci.py` pure functions |
| Create | `cli/tests/test_api_wait.py` | Unit tests for `wait_for_engagement()` |
| Create | `cli/forge_cli/ci.py` | GitHub API calls, markdown formatter, callback poster, threshold logic |
| Modify | `cli/forge_cli/api.py` | Add `import time` at top; add `wait_for_engagement()` method |
| Create | `cli/forge_cli/commands/ci.py` | Click group: `scan` and `report` commands |
| Modify | `cli/forge_cli/main.py` | Import + register `ci_group` |
| Create | `cli/forge_ci_template.yml` | Drop-in GitHub Actions workflow |

---

## Task 1 — Test harness setup

**Files:**
- Create: `cli/tests/__init__.py`
- Modify: `cli/pyproject.toml`

- [ ] **Step 1: Create the tests package**

```bash
mkdir -p /Users/hemparekh/Desktop/FORGE/cli/tests
touch /Users/hemparekh/Desktop/FORGE/cli/tests/__init__.py
```

- [ ] **Step 2: Add pytest and testtools to pyproject.toml**

Open `cli/pyproject.toml` and add under `[project]`:

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Install dev deps**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
/usr/local/bin/python3.14 -m venv .venv314
.venv314/bin/pip install -e ".[dev]" -q
```

Expected: installs forge-cli + pytest.

- [ ] **Step 4: Verify pytest discovers the empty tests package**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/pytest --collect-only
```

Expected: `no tests ran` or `0 items` — no errors.

---

## Task 2 — Unit tests for `ci.py` pure functions (write failing tests first)

**Files:**
- Create: `cli/tests/test_ci.py`

- [ ] **Step 1: Write the test file**

Create `cli/tests/test_ci.py` with this exact content:

```python
"""Unit tests for forge_cli.ci pure functions."""
import pytest
from forge_cli.ci import (
    threshold_breached,
    severity_counts,
    format_findings_markdown,
    build_callback_payload,
)

_FINDINGS = [
    {"severity": "critical", "vulnerability_class": "RCE", "affected_surface": "/cmd"},
    {"severity": "high", "vulnerability_class": "SQLi", "affected_surface": "/api/users"},
    {"severity": "medium", "vulnerability_class": "XSS", "affected_surface": "/search"},
]


# ── threshold_breached ────────────────────────────────────────────────────────

def test_threshold_breached_fail_on_none():
    assert threshold_breached(_FINDINGS, "none") is False


def test_threshold_breached_no_findings():
    assert threshold_breached([], "high") is False


def test_threshold_breached_below_threshold():
    assert threshold_breached([{"severity": "low"}], "high") is False


def test_threshold_breached_at_threshold():
    assert threshold_breached(_FINDINGS, "high") is True


def test_threshold_breached_critical_only():
    assert threshold_breached([{"severity": "critical"}], "critical") is True


def test_threshold_breached_medium_catches_high():
    assert threshold_breached([{"severity": "high"}], "medium") is True


# ── severity_counts ───────────────────────────────────────────────────────────

def test_severity_counts_empty():
    c = severity_counts([])
    assert c == {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}


def test_severity_counts_mixed():
    c = severity_counts(_FINDINGS)
    assert c["critical"] == 1
    assert c["high"] == 1
    assert c["medium"] == 1
    assert c["low"] == 0
    assert c["info"] == 0


# ── format_findings_markdown ──────────────────────────────────────────────────

def test_format_findings_markdown_contains_header():
    md = format_findings_markdown("abc-123", [], "http://localhost:8080")
    assert "## FORGE Security Scan" in md


def test_format_findings_markdown_contains_engagement_link():
    md = format_findings_markdown("abc-123", [], "http://localhost:8080")
    assert "abc-123" in md
    assert "http://localhost:8080" in md


def test_format_findings_markdown_includes_vuln_classes():
    md = format_findings_markdown("abc-123", _FINDINGS, "http://localhost:8080")
    assert "RCE" in md
    assert "SQLi" in md


def test_format_findings_markdown_no_findings_still_valid():
    md = format_findings_markdown("abc-123", [], "http://localhost:8080")
    assert "View full engagement" in md


# ── build_callback_payload ────────────────────────────────────────────────────

def test_build_callback_payload_fields():
    eng = {"id": "abc", "status": "complete", "target_url": "https://example.com"}
    payload = build_callback_payload(eng, _FINDINGS, True)
    assert payload["engagement_id"] == "abc"
    assert payload["status"] == "complete"
    assert payload["findings_count"] == 3
    assert payload["threshold_breached"] is True
    assert payload["severity_counts"]["critical"] == 1
    assert len(payload["findings"]) == 3


def test_build_callback_payload_not_breached():
    eng = {"id": "xyz", "status": "complete", "target_url": "https://example.com"}
    payload = build_callback_payload(eng, [], False)
    assert payload["threshold_breached"] is False
    assert payload["findings_count"] == 0
```

- [ ] **Step 2: Run tests — expect ImportError (module doesn't exist yet)**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/pytest tests/test_ci.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'threshold_breached' from 'forge_cli.ci'` — confirms tests are wired up and failing for the right reason.

---

## Task 3 — Implement `cli/forge_cli/ci.py`

**Files:**
- Create: `cli/forge_cli/ci.py`

- [ ] **Step 1: Create the file**

Create `cli/forge_cli/ci.py` with this exact content:

```python
"""GitHub API integration, markdown formatting, and callback posting for CI/CD."""
from __future__ import annotations
import json
import urllib.error
import urllib.request

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


def threshold_breached(findings: list[dict], fail_on: str) -> bool:
    """Return True if any finding is at or above the fail_on severity level."""
    if fail_on == "none":
        return False
    if fail_on not in SEVERITY_ORDER:
        return False
    cutoff = SEVERITY_ORDER.index(fail_on)
    for f in findings:
        sev = f.get("severity", "info")
        if sev in SEVERITY_ORDER and SEVERITY_ORDER.index(sev) <= cutoff:
            return True
    return False


def severity_counts(findings: list[dict]) -> dict[str, int]:
    """Return a dict of severity → count for all five levels."""
    counts: dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        sev = f.get("severity", "info")
        if sev in counts:
            counts[sev] += 1
    return counts


def format_findings_markdown(
    engagement_id: str,
    findings: list[dict],
    forge_url: str,
) -> str:
    """Build a markdown comment body suitable for GitHub PR/commit comments."""
    counts = severity_counts(findings)

    lines = [
        "## FORGE Security Scan",
        "",
        "| Severity | Count |",
        "|----------|-------|",
    ]
    for sev in SEVERITY_ORDER:
        lines.append(f"| {sev.capitalize()} | {counts[sev]} |")

    # Top findings: prioritise critical/high, fall back to first 5
    top = [f for f in findings if f.get("severity") in ("critical", "high")][:5]
    if not top:
        top = findings[:5]

    if top:
        lines += [
            "",
            "**Top findings:**",
            "",
            "| Severity | Vulnerability | Location |",
            "|----------|--------------|----------|",
        ]
        for f in top:
            sev = f.get("severity", "info").upper()
            vuln = (f.get("vulnerability_class") or f.get("title") or "Finding")[:40]
            loc = f.get("affected_surface", "")[:50]
            lines.append(f"| {sev} | {vuln} | `{loc}` |")

    lines += [
        "",
        f"[View full engagement →]({forge_url.rstrip('/')}/engagements/{engagement_id})",
    ]
    return "\n".join(lines)


def build_callback_payload(
    engagement: dict,
    findings: list[dict],
    breached: bool,
) -> dict:
    """Build the JSON payload for generic CI callback POSTs."""
    return {
        "engagement_id": engagement.get("id", ""),
        "status": engagement.get("status", ""),
        "target_url": engagement.get("target_url", ""),
        "findings_count": len(findings),
        "severity_counts": severity_counts(findings),
        "threshold_breached": breached,
        "findings": findings,
    }


def _github_post(token: str, url: str, body: dict) -> None:
    """POST to the GitHub API. Raises urllib.error.HTTPError on failure."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def post_github_status(
    token: str,
    repo: str,
    sha: str,
    state: str,
    description: str,
    forge_url: str,
    engagement_id: str,
) -> None:
    """Set a GitHub commit status check."""
    _github_post(token, f"https://api.github.com/repos/{repo}/statuses/{sha}", {
        "state": state,
        "description": description[:140],
        "context": "forge / security-scan",
        "target_url": f"{forge_url.rstrip('/')}/engagements/{engagement_id}",
    })


def post_github_comment(
    token: str,
    repo: str,
    sha: str,
    body: str,
    pr: int | None = None,
) -> None:
    """Post a PR comment (if pr is set) or a commit comment."""
    if pr:
        url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments"
    else:
        url = f"https://api.github.com/repos/{repo}/commits/{sha}/comments"
    _github_post(token, url, {"body": body})


def post_callback(callback_url: str, payload: dict) -> None:
    """POST the findings payload to a generic callback URL."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        callback_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()
```

- [ ] **Step 2: Run tests — expect all green**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/pytest tests/test_ci.py -v
```

Expected: 14 tests pass, 0 failures.

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE
git add cli/tests/ cli/forge_cli/ci.py cli/pyproject.toml
git commit -m "feat: add ci.py pure functions with tests (threshold, formatting, callback)"
```

---

## Task 4 — `wait_for_engagement()` in `api.py`

**Files:**
- Create: `cli/tests/test_api_wait.py`
- Modify: `cli/forge_cli/api.py` (add `import time` at top; add method to `ForgeClient`)

- [ ] **Step 1: Write the failing tests**

Create `cli/tests/test_api_wait.py`:

```python
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
        # monotonic: first call sets deadline (0+30=30), subsequent checks return 1
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/pytest tests/test_api_wait.py -v 2>&1 | head -20
```

Expected: `AttributeError: 'ForgeClient' object has no attribute 'wait_for_engagement'`

- [ ] **Step 3: Add `import time` at the top of `api.py`**

In `cli/forge_cli/api.py`, add `import time` after the existing stdlib imports:

```python
"""Thin HTTP client for the FORGE backend API."""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
```

- [ ] **Step 4: Add `wait_for_engagement()` to `ForgeClient`**

In `cli/forge_cli/api.py`, add this method after `stats()`:

```python
    def wait_for_engagement(
        self, eid: str, timeout: int = 1800, poll_interval: int = 15
    ) -> dict:
        """Poll GET /engagements/{eid} until status leaves 'running', or timeout."""
        deadline = time.monotonic() + timeout
        while True:
            eng = self.get_engagement(eid)
            if eng.get("status") != "running":
                return eng
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out after {timeout}s waiting for engagement {eid}"
                )
            time.sleep(poll_interval)
```

- [ ] **Step 5: Run tests — expect all green**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/pytest tests/test_api_wait.py -v
```

Expected: 4 tests pass.

- [ ] **Step 6: Run all tests to confirm nothing broken**

```bash
.venv314/bin/pytest tests/ -v
```

Expected: 18 tests pass total (14 ci + 4 wait).

- [ ] **Step 7: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE
git add cli/forge_cli/api.py cli/tests/test_api_wait.py
git commit -m "feat: add wait_for_engagement() polling method to ForgeClient"
```

---

## Task 5 — `commands/ci.py`

**Files:**
- Create: `cli/forge_cli/commands/ci.py`

- [ ] **Step 1: Create the file**

Create `cli/forge_cli/commands/ci.py` with this exact content:

```python
from __future__ import annotations
import os
import sys

import click

from forge_cli.api import ForgeClient, APIError, _load_config
from forge_cli.display import console, severity_summary, findings_table

SEVERITY_LEVELS = ("critical", "high", "medium", "low", "none")


def _make_client(api_url: str | None, api_key: str | None) -> tuple[ForgeClient, str]:
    cfg = _load_config()
    url = api_url or cfg.get("api_url", "http://localhost:8080")
    key = api_key or cfg.get("api_key")
    return ForgeClient(url, api_key=key), url


def _detect_type(target: str) -> str:
    if target.startswith("http://") or target.startswith("https://"):
        return "web"
    if os.path.isfile(target):
        return "binary"
    return "local_codebase"


@click.group("ci")
def ci_group() -> None:
    """CI/CD integration — scan targets and gate on findings severity."""


@ci_group.command("scan")
@click.argument("target")
@click.option("--type", "target_type", default=None,
              type=click.Choice(["web", "local_codebase", "binary"]),
              help="Target type (auto-detected if omitted).")
@click.option("--fail-on", default="high",
              type=click.Choice(SEVERITY_LEVELS),
              help="Exit 1 if any finding at this severity or above exists. (default: high)")
@click.option("--timeout", default=1800, type=int,
              help="Max seconds to wait for scan completion. (default: 1800)")
@click.option("--poll-interval", default=15, type=int,
              help="Seconds between status polls. (default: 15)")
@click.option("--github-token", default=None, envvar="FORGE_GITHUB_TOKEN",
              help="GitHub PAT. Defaults to FORGE_GITHUB_TOKEN env var.")
@click.option("--repo", default=None, envvar="GITHUB_REPOSITORY",
              help="owner/repo for GitHub feedback. Defaults to GITHUB_REPOSITORY.")
@click.option("--commit", default=None, envvar="GITHUB_SHA",
              help="Commit SHA for GitHub status + comment. Defaults to GITHUB_SHA.")
@click.option("--pr", default=None, type=int, envvar="GITHUB_PR_NUMBER",
              help="PR number to post comment on (falls back to commit comment).")
@click.option("--callback-url", default=None,
              help="POST findings JSON to this URL on completion.")
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def ci_scan(
    target: str,
    target_type: str | None,
    fail_on: str,
    timeout: int,
    poll_interval: int,
    github_token: str | None,
    repo: str | None,
    commit: str | None,
    pr: int | None,
    callback_url: str | None,
    api_url: str | None,
    api_key: str | None,
) -> None:
    """Run a security scan and exit non-zero if findings breach --fail-on threshold.

    \b
    Examples:
      forge ci scan https://app.example.com --fail-on high
      forge ci scan /path/to/project --fail-on critical
      forge ci scan https://app.example.com \\
        --github-token $GITHUB_TOKEN --repo owner/repo --commit $GITHUB_SHA
    """
    from forge_cli.ci import (
        threshold_breached, format_findings_markdown,
        build_callback_payload, post_github_status,
        post_github_comment, post_callback, severity_counts,
    )

    client, forge_url = _make_client(api_url, api_key)

    if target_type is None:
        target_type = _detect_type(target)

    target_url = target if target_type == "web" else "local"
    target_path = None if target_type == "web" else os.path.abspath(target)

    # ── Create engagement ──────────────────────────────────────────────────
    console.print(f"[bold]FORGE CI Scan[/bold]: [cyan]{target}[/cyan] [dim]({target_type})[/dim]")
    try:
        eng = client.create_engagement(
            target_url=target_url,
            target_type=target_type,
            target_path=target_path,
        )
    except (APIError, ConnectionError) as e:
        console.print(f"[red]Error:[/red] {e}", err=True)
        sys.exit(1)

    eid = eng["id"]
    console.print(f"[dim]Engagement:[/dim] {eid}")

    # ── Start ──────────────────────────────────────────────────────────────
    try:
        client.start_engagement(eid)
    except (APIError, ConnectionError) as e:
        console.print(f"[red]Error:[/red] {e}", err=True)
        sys.exit(1)

    console.print(
        f"[green]✓[/green] Pipeline started — "
        f"polling every {poll_interval}s (timeout: {timeout}s)\n"
    )

    # ── Wait ───────────────────────────────────────────────────────────────
    try:
        engagement = client.wait_for_engagement(eid, timeout=timeout, poll_interval=poll_interval)
    except TimeoutError as e:
        console.print(f"[red]✗ Timed out:[/red] {e}", err=True)
        sys.exit(1)
    except (APIError, ConnectionError) as e:
        console.print(f"[red]Error:[/red] {e}", err=True)
        sys.exit(1)

    if engagement.get("status") == "aborted":
        console.print("[red]✗ Engagement was aborted before completing.[/red]", err=True)
        sys.exit(1)

    # ── Fetch findings ─────────────────────────────────────────────────────
    try:
        raw = client._request("GET", f"/api/v1/engagements/{eid}/findings")
        all_findings = raw if isinstance(raw, list) else []
    except (APIError, ConnectionError):
        all_findings = []

    # ── Print summary ──────────────────────────────────────────────────────
    if all_findings:
        console.print(severity_summary(all_findings))
        console.print(findings_table(all_findings))
    else:
        console.print("[dim]No findings.[/dim]")

    breached = threshold_breached(all_findings, fail_on)
    counts = severity_counts(all_findings)
    desc = " · ".join(
        f"{counts[s]} {s}" for s in ("critical", "high", "medium") if counts[s]
    ) or "no findings"

    if breached:
        console.print(f"\n[bold red]✗ Threshold breached[/bold red] — {desc} (--fail-on {fail_on})")
    else:
        console.print(f"\n[bold green]✓ Clean[/bold green] — {desc}")

    # ── GitHub feedback ────────────────────────────────────────────────────
    if github_token and repo and commit:
        state = "failure" if breached else "success"
        try:
            post_github_status(github_token, repo, commit, state, desc, forge_url, eid)
            console.print("[dim]  GitHub status check posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] GitHub status failed: {e}", err=True)

        try:
            body = format_findings_markdown(eid, all_findings, forge_url)
            post_github_comment(github_token, repo, commit, body, pr=pr)
            console.print("[dim]  GitHub comment posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] GitHub comment failed: {e}", err=True)

    # ── Generic callback ───────────────────────────────────────────────────
    if callback_url:
        try:
            payload = build_callback_payload(engagement, all_findings, breached)
            post_callback(callback_url, payload)
            console.print("[dim]  Callback posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Callback failed: {e}", err=True)

    sys.exit(1 if breached else 0)


@ci_group.command("report")
@click.argument("engagement_id")
@click.option("--fail-on", default="high", type=click.Choice(SEVERITY_LEVELS))
@click.option("--github-token", default=None, envvar="FORGE_GITHUB_TOKEN")
@click.option("--repo", default=None, envvar="GITHUB_REPOSITORY")
@click.option("--commit", default=None, envvar="GITHUB_SHA")
@click.option("--pr", default=None, type=int, envvar="GITHUB_PR_NUMBER")
@click.option("--callback-url", default=None)
@click.option("--api-url", default=None)
@click.option("--api-key", default=None)
def ci_report(
    engagement_id: str,
    fail_on: str,
    github_token: str | None,
    repo: str | None,
    commit: str | None,
    pr: int | None,
    callback_url: str | None,
    api_url: str | None,
    api_key: str | None,
) -> None:
    """Post results for an already-finished engagement to GitHub or a callback URL.

    \b
    Examples:
      forge ci report <engagement-id> \\
        --github-token $GITHUB_TOKEN --repo owner/repo --commit $SHA
    """
    from forge_cli.ci import (
        threshold_breached, format_findings_markdown,
        build_callback_payload, post_github_status,
        post_github_comment, post_callback, severity_counts,
    )

    client, forge_url = _make_client(api_url, api_key)

    try:
        engagement = client.get_engagement(engagement_id)
        raw = client._request("GET", f"/api/v1/engagements/{engagement_id}/findings")
        all_findings = raw if isinstance(raw, list) else []
    except (APIError, ConnectionError) as e:
        raise click.ClickException(str(e))

    breached = threshold_breached(all_findings, fail_on)
    counts = severity_counts(all_findings)
    desc = " · ".join(
        f"{counts[s]} {s}" for s in ("critical", "high", "medium") if counts[s]
    ) or "no findings"

    if github_token and repo and commit:
        state = "failure" if breached else "success"
        try:
            post_github_status(github_token, repo, commit, state, desc, forge_url, engagement_id)
            console.print("[dim]  GitHub status check posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] GitHub status failed: {e}", err=True)

        try:
            body = format_findings_markdown(engagement_id, all_findings, forge_url)
            post_github_comment(github_token, repo, commit, body, pr=pr)
            console.print("[dim]  GitHub comment posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] GitHub comment failed: {e}", err=True)

    if callback_url:
        try:
            payload = build_callback_payload(engagement, all_findings, breached)
            post_callback(callback_url, payload)
            console.print("[dim]  Callback posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Callback failed: {e}", err=True)

    console.print(f"[green]✓[/green] Reported: {desc}")
```

- [ ] **Step 2: Verify the file parses without errors**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/python -c "from forge_cli.commands.ci import ci_group; print('OK')"
```

Expected: `OK`

---

## Task 6 — Wire `ci_group` into `main.py`

**Files:**
- Modify: `cli/forge_cli/main.py`

- [ ] **Step 1: Add import**

In `cli/forge_cli/main.py`, extend the existing commands import block (currently importing from `commands.auth` and `commands.users`) to add:

```python
from forge_cli.commands.auth import register, login, whoami, logout, api_keys_group
from forge_cli.commands.users import users_group
from forge_cli.commands.ci import ci_group
```

- [ ] **Step 2: Register the command**

In `cli/forge_cli/main.py`, extend the existing `cli.add_command(...)` block to add:

```python
cli.add_command(register)
cli.add_command(login)
cli.add_command(whoami)
cli.add_command(logout)
cli.add_command(api_keys_group)
cli.add_command(users_group)
cli.add_command(ci_group)
```

- [ ] **Step 3: Reinstall and verify `forge --help`**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/pip install -e . -q
.venv314/bin/forge --help
```

Expected output includes `ci` in the Commands list:
```
Commands:
  api-keys  ...
  ci        CI/CD integration — scan targets and gate on findings severity.
  configure ...
  ...
```

- [ ] **Step 4: Check subcommands**

```bash
.venv314/bin/forge ci --help
```

Expected:
```
Usage: forge ci [OPTIONS] COMMAND [ARGS]...

  CI/CD integration — scan targets and gate on findings severity.

Commands:
  report  Post results for an already-finished engagement...
  scan    Run a security scan and exit non-zero if findings...
```

```bash
.venv314/bin/forge ci scan --help
.venv314/bin/forge ci report --help
```

Expected: full option lists for both commands, no errors.

- [ ] **Step 5: Run all tests to confirm nothing regressed**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/pytest tests/ -v
```

Expected: 18 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE
git add cli/forge_cli/commands/ci.py cli/forge_cli/main.py
git commit -m "feat: add forge ci scan/report commands for CI/CD integration"
```

---

## Task 7 — GitHub Actions workflow template

**Files:**
- Create: `cli/forge_ci_template.yml`

- [ ] **Step 1: Create the template**

Create `cli/forge_ci_template.yml`:

```yaml
# FORGE Security Scan — GitHub Actions workflow template
#
# Copy this file to .github/workflows/forge-scan.yml in your repo.
#
# Required repository configuration:
#   Variables (Settings → Secrets and variables → Actions → Variables):
#     TARGET_URL   — the URL or path to scan, e.g. https://app.yourcompany.com
#     FORGE_API_URL — your FORGE backend, e.g. https://forge.yourcompany.com
#   Secrets:
#     FORGE_API_KEY — an API key from: forge api-keys create ci

name: FORGE Security Scan

on:
  push:
    branches: [main, master]

jobs:
  forge-scan:
    runs-on: ubuntu-latest
    permissions:
      statuses: write      # post commit status check
      issues: write        # post PR comment (if --pr is set)

    steps:
      - uses: actions/checkout@v4

      - name: Install FORGE CLI
        run: pip install forge-cli

      - name: Run security scan
        run: |
          forge ci scan "$TARGET_URL" \
            --fail-on high \
            --github-token "$GITHUB_TOKEN" \
            --repo "$GITHUB_REPOSITORY" \
            --commit "$GITHUB_SHA"
        env:
          TARGET_URL: ${{ vars.TARGET_URL }}
          FORGE_API_URL: ${{ vars.FORGE_API_URL }}
          FORGE_API_KEY: ${{ secrets.FORGE_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Verify the YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('/Users/hemparekh/Desktop/FORGE/cli/forge_ci_template.yml'))" 2>/dev/null && echo "valid YAML" || python3 -c "print('pyyaml not installed, skipping parse check')"
```

Expected: `valid YAML` or the skip message (both are fine).

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE
git add cli/forge_ci_template.yml
git commit -m "feat: add GitHub Actions workflow template for FORGE CI integration"
```

---

## Task 8 — Push and update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a CI/CD section to the README**

In `README.md`, find the existing `## CLI (forge)` section and add a new subsection after the existing `### Typical workflow` block. Insert:

```markdown
### CI/CD Integration

`forge ci scan` runs a FORGE security scan from any CI pipeline and exits non-zero if findings breach the severity threshold. Native GitHub feedback (commit status check + PR/commit comment) is included when `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, and `GITHUB_SHA` are set.

#### GitHub Actions (quickstart)

Copy `cli/forge_ci_template.yml` to `.github/workflows/forge-scan.yml`, then set:

| Setting | Where | Value |
|---------|-------|-------|
| `TARGET_URL` | Repo variable | URL or path to scan |
| `FORGE_API_URL` | Repo variable | Your FORGE backend URL |
| `FORGE_API_KEY` | Repo secret | From `forge api-keys create ci` |

The workflow triggers on push to `main`/`master`, posts a commit status check (✓ / ✗), and adds a findings summary comment on the commit.

#### Generic CI (GitLab, Jenkins, etc.)

```bash
forge ci scan "$TARGET_URL" --fail-on high --callback-url "$RESULTS_WEBHOOK"
```

`--callback-url` receives a JSON POST with the full findings payload when the scan completes.

#### Manual usage

```bash
# Scan a web app, fail if any high+ finding
forge ci scan https://app.example.com --fail-on high

# Scan a local codebase, informational only (never fails build)
forge ci scan /path/to/project --fail-on none

# Post results for an existing engagement to GitHub
forge ci report <engagement-id> \
  --github-token $GITHUB_TOKEN --repo owner/repo --commit $SHA
```
```

- [ ] **Step 2: Commit and push everything**

```bash
cd /Users/hemparekh/Desktop/FORGE
git add README.md
git commit -m "docs: add CI/CD integration section to README"
git push origin main
```

Expected: push succeeds, all commits land on main.

- [ ] **Step 3: Final smoke test — all new commands present**

```bash
cd /Users/hemparekh/Desktop/FORGE/cli
.venv314/bin/forge --help | grep ci
.venv314/bin/forge ci scan --help | grep fail-on
.venv314/bin/forge ci report --help | grep github-token
```

Expected:
```
ci        CI/CD integration — scan targets and gate on findings severity.
  --fail-on [critical|high|medium|low|none]
  --github-token TEXT
```
