"""FORGE CLI — command-line interface for the FORGE pentesting platform."""
from __future__ import annotations
import json
import os
import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.columns import Columns

from forge_cli.api import ForgeClient, APIError
from forge_cli.display import (
    console, engagement_table, findings_table, severity_summary,
    STATUS_COLORS, TARGET_ICONS,
)

DEFAULT_API = os.environ.get("FORGE_API_URL", "http://localhost:8080")


def get_client(ctx) -> ForgeClient:
    return ForgeClient(ctx.obj.get("api_url", DEFAULT_API))


def err(msg: str):
    console.print(f"[bold red]Error:[/bold red] {msg}")
    sys.exit(1)


@click.group()
@click.option("--api-url", default=DEFAULT_API, envvar="FORGE_API_URL",
              help="FORGE backend URL (default: http://localhost:8080)")
@click.pass_context
def cli(ctx, api_url):
    """FORGE — Framework for Offensive Reasoning, Generation and Exploitation

    Multi-agent autonomous pentesting platform.
    """
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url


# ── forge run ───────────────────────────────────────────────────────────────

@cli.command()
@click.argument("target")
@click.option("--type", "target_type", default=None,
              type=click.Choice(["web", "local_codebase", "binary"]),
              help="Target type (auto-detected if omitted)")
@click.option("--scope", multiple=True, help="In-scope paths (web targets)")
@click.option("--out-of-scope", multiple=True, help="Out-of-scope paths (web targets)")
@click.option("--no-stream", is_flag=True, help="Don't stream live events, just start and exit")
@click.pass_context
def run(ctx, target, target_type, scope, out_of_scope, no_stream):
    """Start a pentest against TARGET.

    TARGET can be a URL (web) or an absolute filesystem path (local codebase/binary).

    \b
    Examples:
      forge run https://example.com
      forge run /Users/you/Desktop/myproject
      forge run /usr/bin/target-binary --type binary
    """
    client = get_client(ctx)

    # Auto-detect type
    if target_type is None:
        if target.startswith("http://") or target.startswith("https://"):
            target_type = "web"
        elif os.path.isfile(target):
            target_type = "binary"
        else:
            target_type = "local_codebase"

    # Validate
    if target_type in ("local_codebase", "binary"):
        if not os.path.exists(target):
            err(f"Path does not exist: {target}")
        target_path = os.path.abspath(target)
        target_url = "local"
    else:
        target_path = None
        target_url = target

    # Check backend health
    try:
        client.health()
    except ConnectionError as e:
        err(str(e))

    icon = TARGET_ICONS.get(target_type, "")
    console.print(Panel(
        f"[bold orange1]Target:[/bold orange1] {icon} [cyan]{target}[/cyan]\n"
        f"[bold orange1]Type:[/bold orange1]   {target_type}",
        title="[bold]FORGE[/bold] — Starting Engagement",
        border_style="orange1",
    ))

    # Create engagement
    try:
        eng = client.create_engagement(
            target_url=target_url,
            target_type=target_type,
            target_path=target_path,
            scope=list(scope) or None,
            out_of_scope=list(out_of_scope) or None,
        )
    except APIError as e:
        err(str(e))

    eid = eng["id"]
    console.print(f"[dim]Engagement ID:[/dim] [bold]{eid}[/bold]")

    # Start
    try:
        client.start_engagement(eid)
    except APIError as e:
        err(str(e))

    console.print("[green]✓[/green] Pipeline started\n")

    if no_stream:
        console.print(f"[dim]Monitor:[/dim]  forge status {eid}")
        console.print(f"[dim]Findings:[/dim] forge findings {eid}")
        return

    # Stream live events
    console.print("[bold]Live event stream[/bold] [dim](Ctrl+C to detach)[/dim]\n")
    from forge_cli.stream import stream_events
    stream_events(eid, ctx.obj["api_url"])

    # Show summary after completion
    console.print()
    _print_findings_summary(client, eid)


# ── forge list ──────────────────────────────────────────────────────────────

@cli.command("list")
@click.pass_context
def list_engagements(ctx):
    """List all engagements."""
    client = get_client(ctx)
    try:
        engagements = client.list_engagements()
    except (APIError, ConnectionError) as e:
        err(str(e))

    if not engagements:
        console.print("[dim]No engagements yet. Run: forge run <target>[/dim]")
        return

    console.print(engagement_table(engagements))
    console.print(f"[dim]{len(engagements)} engagement(s)[/dim]")


# ── forge status ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("engagement_id")
@click.option("--watch", "-w", is_flag=True, help="Stream live events")
@click.pass_context
def status(ctx, engagement_id, watch):
    """Show status of an engagement. Use --watch to stream live events."""
    client = get_client(ctx)
    try:
        eng = client.get_engagement(engagement_id)
    except (APIError, ConnectionError) as e:
        err(str(e))

    _print_engagement(eng)

    if watch and eng.get("status") == "running":
        console.print("\n[bold]Live event stream[/bold] [dim](Ctrl+C to detach)[/dim]\n")
        from forge_cli.stream import stream_events
        stream_events(engagement_id, ctx.obj["api_url"])
        _print_findings_summary(client, engagement_id)


# ── forge findings ───────────────────────────────────────────────────────────

@cli.command()
@click.argument("engagement_id")
@click.option("--severity", type=click.Choice(["critical", "high", "medium", "low", "info"]),
              help="Filter by severity")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
@click.option("--output", "-o", type=click.Path(), help="Save JSON to file")
@click.pass_context
def findings(ctx, engagement_id, severity, as_json, output):
    """Show findings for an engagement."""
    client = get_client(ctx)

    # Fetch findings via backend DB query — use knowledge endpoint as proxy
    # We hit /api/v1/engagements/{id} to get the engagement, then note findings
    # are stored in the Finding model — no direct findings list API yet, so
    # we use the stats + a direct DB query workaround via /system/stats
    # For now, fetch from the engagement's WS cache or use the /findings sub-path
    try:
        raw = client._request("GET", f"/api/v1/engagements/{engagement_id}/findings")
    except APIError as e:
        if e.status == 404:
            # Endpoint doesn't exist yet — inform user
            err("Findings API not available. Use the UI at http://localhost:5174 or export via Report Viewer.")
        err(str(e))
    except ConnectionError as e:
        err(str(e))

    all_findings = raw if isinstance(raw, list) else []

    if severity:
        all_findings = [f for f in all_findings if f.get("severity") == severity]

    if as_json or output:
        data = json.dumps(all_findings, indent=2)
        if output:
            with open(output, "w") as f:
                f.write(data)
            console.print(f"[green]✓[/green] Saved {len(all_findings)} findings to [cyan]{output}[/cyan]")
        else:
            click.echo(data)
        return

    if not all_findings:
        console.print("[dim]No findings yet.[/dim]")
        return

    console.print(severity_summary(all_findings))
    console.print(findings_table(all_findings))


# ── forge gate ───────────────────────────────────────────────────────────────

@cli.group()
def gate():
    """Manage human gate decisions."""


@gate.command("approve")
@click.argument("engagement_id")
@click.option("--notes", default="", help="Approval notes")
@click.pass_context
def gate_approve(ctx, engagement_id, notes):
    """Approve a human gate to continue the engagement."""
    client = get_client(ctx)
    try:
        eng = client.gate_decide(engagement_id, approved=True, notes=notes)
        console.print(f"[green]✓[/green] Gate approved — status: [bold]{eng['gate_status']}[/bold]")
    except (APIError, ConnectionError) as e:
        err(str(e))


@gate.command("reject")
@click.argument("engagement_id")
@click.option("--notes", default="", help="Rejection notes")
@click.pass_context
def gate_reject(ctx, engagement_id, notes):
    """Reject a gate and abort the engagement."""
    client = get_client(ctx)
    try:
        eng = client.gate_decide(engagement_id, approved=False, notes=notes)
        console.print(f"[red]✗[/red] Gate rejected — status: [bold]{eng['status']}[/bold]")
    except (APIError, ConnectionError) as e:
        err(str(e))


# ── forge report ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("engagement_id")
@click.option("--output", "-o", type=click.Path(), help="Save markdown report to file")
@click.pass_context
def report(ctx, engagement_id, output):
    """Generate a markdown report for an engagement."""
    client = get_client(ctx)
    try:
        eng = client.get_engagement(engagement_id)
    except (APIError, ConnectionError) as e:
        err(str(e))

    target = eng.get("target_path") or eng.get("target_url", "")
    ttype = eng.get("target_type", "web")
    lines = [
        f"# FORGE Security Assessment Report",
        f"",
        f"**Target:** {target}",
        f"**Type:** {ttype}",
        f"**Status:** {eng.get('status')}",
        f"**Started:** {eng.get('created_at', '')[:19]}",
        f"**Completed:** {(eng.get('completed_at') or '')[:19] or 'N/A'}",
        f"**Engagement ID:** {engagement_id}",
        f"",
        f"---",
        f"",
    ]

    try:
        raw = client._request("GET", f"/api/v1/engagements/{engagement_id}/findings")
        all_findings = raw if isinstance(raw, list) else []
    except Exception:
        all_findings = []

    counts: dict[str, int] = {}
    for f in all_findings:
        sev = f.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1

    lines += [
        f"## Summary",
        f"",
        f"| Severity | Count |",
        f"|----------|-------|",
    ]
    for sev in ("critical", "high", "medium", "low", "info"):
        if counts.get(sev):
            lines.append(f"| {sev.capitalize()} | {counts[sev]} |")
    lines += ["", f"**Total:** {len(all_findings)} findings", "", "---", ""]

    if all_findings:
        lines.append("## Findings")
        lines.append("")
        for i, f in enumerate(all_findings, 1):
            sev = f.get("severity", "info").upper()
            vuln = f.get("vulnerability_class", f.get("title", "Finding"))
            loc = f.get("affected_surface", f.get("endpoint", ""))
            desc = f.get("description", "")
            evidence = f.get("evidence", "")
            rec = f.get("recommendation", "")
            lines += [
                f"### {i}. [{sev}] {vuln}",
                f"",
                f"**Location:** `{loc}`",
                f"",
                f"**Description:** {desc}",
                f"",
            ]
            if evidence:
                ev = evidence if isinstance(evidence, str) else json.dumps(evidence)
                lines += [f"**Evidence:**", f"```", ev[:500], f"```", ""]
            if rec:
                lines += [f"**Recommendation:** {rec}", ""]
            lines.append("---")
            lines.append("")

    md = "\n".join(lines)

    if output:
        with open(output, "w") as fh:
            fh.write(md)
        console.print(f"[green]✓[/green] Report saved to [cyan]{output}[/cyan]")
    else:
        click.echo(md)


# ── forge delete ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("engagement_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def delete(ctx, engagement_id, yes):
    """Delete an engagement."""
    client = get_client(ctx)
    if not yes:
        click.confirm(f"Delete engagement {engagement_id}?", abort=True)
    try:
        client.delete_engagement(engagement_id)
        console.print(f"[green]✓[/green] Deleted {engagement_id}")
    except (APIError, ConnectionError) as e:
        err(str(e))


# ── forge stats ──────────────────────────────────────────────────────────────

@cli.command()
@click.pass_context
def stats(ctx):
    """Show platform statistics."""
    client = get_client(ctx)
    try:
        s = client.stats()
    except (APIError, ConnectionError) as e:
        err(str(e))

    console.print(Panel(
        f"[bold]Engagements:[/bold]     {s.get('engagements', 0)}\n"
        f"[bold]Findings:[/bold]        {s.get('findings', 0)}\n"
        f"[bold]Knowledge entries:[/bold] {s.get('knowledge_entries', 0)}",
        title="[bold]FORGE Stats[/bold]",
        border_style="orange1",
    ))


# ── helpers ───────────────────────────────────────────────────────────────────

def _print_engagement(eng: dict):
    status = eng.get("status", "")
    scolor = STATUS_COLORS.get(status, "")
    ttype = eng.get("target_type", "web")
    icon = TARGET_ICONS.get(ttype, "")
    target = eng.get("target_path") or eng.get("target_url", "")

    console.print(Panel(
        f"[bold orange1]ID:[/bold orange1]      {eng['id']}\n"
        f"[bold orange1]Target:[/bold orange1]  {icon} {target}\n"
        f"[bold orange1]Type:[/bold orange1]    {ttype}\n"
        f"[bold orange1]Status:[/bold orange1]  [{scolor}]{status}[/{scolor}]\n"
        f"[bold orange1]Gate:[/bold orange1]    {eng.get('gate_status', '')}\n"
        f"[bold orange1]Created:[/bold orange1] {eng.get('created_at', '')[:19]}",
        title="[bold]Engagement[/bold]",
        border_style="orange1",
    ))


def _print_findings_summary(client: ForgeClient, eid: str):
    try:
        raw = client._request("GET", f"/api/v1/engagements/{eid}/findings")
        findings_list = raw if isinstance(raw, list) else []
        if findings_list:
            console.print(severity_summary(findings_list))
            console.print(f"\n[dim]Full details:[/dim] forge findings {eid}")
            console.print(f"[dim]Export:[/dim]      forge findings {eid} --output report.json")
            console.print(f"[dim]Report:[/dim]      forge report {eid} --output report.md")
    except Exception:
        s = client.stats()
        n = s.get("findings", 0)
        if n:
            console.print(f"\n[bold green]{n} findings[/bold green] discovered.")
            console.print(f"[dim]View:[/dim] forge findings {eid}")


if __name__ == "__main__":
    cli()
