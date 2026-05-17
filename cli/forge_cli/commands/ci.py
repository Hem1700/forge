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
        console.print(f"[red]Error:[/red] {e}", stderr=True)
        sys.exit(1)

    eid = eng["id"]
    console.print(f"[dim]Engagement:[/dim] {eid}")

    # ── Start ──────────────────────────────────────────────────────────────
    try:
        client.start_engagement(eid)
    except (APIError, ConnectionError) as e:
        console.print(f"[red]Error:[/red] {e}", stderr=True)
        sys.exit(1)

    console.print(
        f"[green]✓[/green] Pipeline started — "
        f"polling every {poll_interval}s (timeout: {timeout}s)\n"
    )

    # ── Wait ───────────────────────────────────────────────────────────────
    try:
        engagement = client.wait_for_engagement(eid, timeout=timeout, poll_interval=poll_interval)
    except TimeoutError as e:
        console.print(f"[red]✗ Timed out:[/red] {e}", stderr=True)
        sys.exit(1)
    except (APIError, ConnectionError) as e:
        console.print(f"[red]Error:[/red] {e}", stderr=True)
        sys.exit(1)

    if engagement.get("status") == "aborted":
        console.print("[red]✗ Engagement was aborted before completing.[/red]", stderr=True)
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
            console.print(f"[yellow]Warning:[/yellow] GitHub status failed: {e}", stderr=True)

        try:
            body = format_findings_markdown(eid, all_findings, forge_url)
            post_github_comment(github_token, repo, commit, body, pr=pr)
            console.print("[dim]  GitHub comment posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] GitHub comment failed: {e}", stderr=True)

    # ── Generic callback ───────────────────────────────────────────────────
    if callback_url:
        try:
            payload = build_callback_payload(engagement, all_findings, breached)
            post_callback(callback_url, payload)
            console.print("[dim]  Callback posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Callback failed: {e}", stderr=True)

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
            console.print(f"[yellow]Warning:[/yellow] GitHub status failed: {e}", stderr=True)

        try:
            body = format_findings_markdown(engagement_id, all_findings, forge_url)
            post_github_comment(github_token, repo, commit, body, pr=pr)
            console.print("[dim]  GitHub comment posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] GitHub comment failed: {e}", stderr=True)

    if callback_url:
        try:
            payload = build_callback_payload(engagement, all_findings, breached)
            post_callback(callback_url, payload)
            console.print("[dim]  Callback posted.[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Callback failed: {e}", stderr=True)

    console.print(f"[green]✓[/green] Reported: {desc}")
