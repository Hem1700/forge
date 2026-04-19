"""FORGE CLI — command-line interface for the FORGE pentesting platform."""
from __future__ import annotations
import json
import os
import sys
from typing import NoReturn
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


def err(msg: str) -> NoReturn:
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
@click.option("--exploit", "show_exploit", is_flag=True,
              help="Generate and show exploit walkthrough for each finding")
@click.option("--poc", "show_poc", is_flag=True,
              help="Generate and save PoC script for each finding")
@click.option("--execute", "show_execute", is_flag=True,
              help="Generate script and execute exploit for each finding (prompts per finding)")
@click.pass_context
def findings(ctx, engagement_id, severity, as_json, output, show_exploit, show_poc, show_execute):
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

    # If --exploit flag: generate and print exploit for each finding
    if show_exploit and all_findings and not as_json and not output:
        from forge_cli.display import render_exploit
        for f in all_findings:
            fid = f.get('id')
            if not fid:
                continue
            console.print(f"\n[dim]Generating exploit for {fid[:8]}…[/dim]")
            try:
                exploit_data = client._request("POST", f"/api/v1/findings/{fid}/exploit", timeout=120)
                render_exploit(f, exploit_data)
            except (APIError, ConnectionError) as e:
                console.print(f"[red]Failed for {fid[:8]}: {e}[/red]")

    # If --poc flag: generate and save PoC for each finding
    if show_poc and all_findings and not as_json and not output:
        from forge_cli.display import render_poc
        for f in all_findings:
            fid = f.get('id')
            if not fid:
                continue
            console.print(f"\n[dim]Generating PoC for {fid[:8]}…[/dim]")
            try:
                poc_data = client._request("POST", f"/api/v1/findings/{fid}/poc", timeout=120)
                render_poc(f, poc_data)
            except (APIError, ConnectionError) as e:
                console.print(f"[red]Failed for {fid[:8]}: {e}[/red]")

    # If --execute flag: generate script and execute exploit for each finding
    if show_execute and all_findings and not as_json and not output:
        from forge_cli.display import render_execution
        for f in all_findings:
            fid = f.get('id')
            if not fid:
                continue
            target = f.get('affected_surface', fid[:8])
            console.print(f"\n[bold yellow]⚠  Execute exploit for [{f.get('severity','').upper()}] {f.get('vulnerability_class','Finding')} — {target}?[/bold yellow]")
            if not click.confirm("  Proceed?", default=False):
                console.print("[dim]Skipped.[/dim]")
                continue
            with console.status("[bold red]Executing…[/bold red]"):
                try:
                    execution = client._request(
                        "POST",
                        f"/api/v1/findings/{fid}/exploit/execute",
                        timeout=90,
                        json_body={"confirmed": True},
                    )
                    render_execution(f, execution)
                except (APIError, ConnectionError) as e:
                    console.print(f"[red]Failed for {fid[:8]}: {e}[/red]")


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


# ── forge exploit ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("finding_id")
@click.pass_context
def exploit(ctx, finding_id):
    """Generate and display exploit walkthrough for a finding.

    \b
    Examples:
      forge exploit <finding-id>
    """
    client = get_client(ctx)

    try:
        finding = client._request("GET", f"/api/v1/findings/{finding_id}")
    except APIError as e:
        err(str(e))
    except ConnectionError as e:
        err(str(e))

    with console.status("[bold orange1]Generating exploit intelligence…[/bold orange1]"):
        try:
            exploit_data = client._request("POST", f"/api/v1/findings/{finding_id}/exploit", timeout=120)
        except APIError as e:
            err(str(e))
        except ConnectionError as e:
            err(str(e))

    from forge_cli.display import render_exploit
    render_exploit(finding, exploit_data)


# ── forge poc ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("finding_id")
@click.pass_context
def poc(ctx, finding_id):
    """Generate and save PoC exploit script for a finding.

    \b
    Examples:
      forge poc <finding-id>
    """
    client = get_client(ctx)

    try:
        finding = client._request("GET", f"/api/v1/findings/{finding_id}")
    except APIError as e:
        err(str(e))
    except ConnectionError as e:
        err(str(e))

    with console.status("[bold orange1]Generating PoC script…[/bold orange1]"):
        try:
            poc_data = client._request("POST", f"/api/v1/findings/{finding_id}/poc", timeout=120)
        except APIError as e:
            err(str(e))
        except ConnectionError as e:
            err(str(e))

    from forge_cli.display import render_poc
    render_poc(finding, poc_data)


# ── forge exploit-script ──────────────────────────────────────────────────────

@cli.command("exploit-script")
@click.argument("finding_id")
@click.pass_context
def exploit_script(ctx, finding_id):
    """Generate and save a weaponized exploit script for a finding.

    \b
    Examples:
      forge exploit-script <finding-id>
    """
    client = get_client(ctx)

    try:
        finding = client._request("GET", f"/api/v1/findings/{finding_id}")
    except APIError as e:
        err(str(e))
    except ConnectionError as e:
        err(str(e))

    with console.status("[bold red]Generating weaponized exploit script…[/bold red]"):
        try:
            script_data = client._request("POST", f"/api/v1/findings/{finding_id}/exploit/generate", timeout=120)
        except APIError as e:
            err(str(e))
        except ConnectionError as e:
            err(str(e))

    from forge_cli.display import render_exploit_script
    render_exploit_script(finding, script_data)


# ── forge execute ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("finding_id")
@click.option("--confirm", "skip_prompt", is_flag=True,
              help="Skip interactive confirmation prompt (for scripted use)")
@click.pass_context
def execute(ctx, finding_id, skip_prompt):
    """Execute a weaponized exploit against the real target.

    Generates the exploit script if not already cached, then runs it in an
    isolated Docker container and prints the LLM verdict.

    \b
    Examples:
      forge execute <finding-id>
      forge execute <finding-id> --confirm
    """
    client = get_client(ctx)

    try:
        finding = client._request("GET", f"/api/v1/findings/{finding_id}")
    except APIError as e:
        err(str(e))
    except ConnectionError as e:
        err(str(e))

    # Get or generate script to show impact statement
    script_data = finding.get("exploit_script")
    if not script_data:
        with console.status("[bold red]Generating weaponized exploit script…[/bold red]"):
            try:
                script_data = client._request("POST", f"/api/v1/findings/{finding_id}/exploit/generate", timeout=120)
            except APIError as e:
                err(str(e))
            except ConnectionError as e:
                err(str(e))

    target = finding.get("affected_surface", "target")
    impact = script_data.get("impact_achieved", "Unknown impact")

    console.print(f"\n[bold yellow]⚠  This will execute a live exploit against:[/bold yellow] [cyan]{target}[/cyan]")
    console.print(f"[bold red]Impact:[/bold red] {impact}")

    if not skip_prompt:
        if not click.confirm("\n  Execute?", default=False):
            console.print("[dim]Aborted.[/dim]")
            return

    console.print("\n[dim]Executing exploit…[/dim]\n")

    with console.status("[bold red]Running exploit in Docker container…[/bold red]"):
        try:
            execution = client._request(
                "POST",
                f"/api/v1/findings/{finding_id}/exploit/execute",
                timeout=90,
                json_body={"confirmed": True},
            )
        except APIError as e:
            err(str(e))
        except ConnectionError as e:
            err(str(e))

    from forge_cli.display import render_execution
    render_execution(finding, execution)


# ── forge report ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("engagement_id")
@click.option("--output", "-o", type=click.Path(), help="Save markdown report to file")
@click.option("--pdf", "as_pdf", is_flag=True, help="Generate PDF report via Playwright and save to file")
@click.pass_context
def report(ctx, engagement_id, output, as_pdf):
    """Generate a report for an engagement.

    Without flags: prints markdown to stdout (or saves with --output).
    With --pdf: generates a PDF via the backend and saves to ./forge_report_<id>.pdf.

    \b
    Examples:
      forge report <engagement-id>
      forge report <engagement-id> --output report.md
      forge report <engagement-id> --pdf
    """
    client = get_client(ctx)

    if as_pdf:
        console.print("[bold]Generating PDF report…[/bold]")
        try:
            pdf_bytes = client._request_bytes(
                "POST", f"/api/v1/engagements/{engagement_id}/report/pdf", timeout=120
            )
            filename = f"./forge_report_{engagement_id}.pdf"
            with open(filename, "wb") as fh:
                fh.write(pdf_bytes)
            console.print(f"[green]✓[/green] Saved to: [cyan]{filename}[/cyan]")
        except (APIError, ConnectionError) as e:
            err(str(e))
        except OSError as e:
            err(f"Could not write {filename}: {e}")
        return

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
            # Exploit walkthrough (if generated)
            exploit_detail = f.get("exploit_detail")
            if exploit_detail:
                lines += [f"**Difficulty:** {exploit_detail.get('difficulty', 'unknown')}", ""]
                lines += [f"**Impact:** {exploit_detail.get('impact', '')}", ""]
                prereqs = exploit_detail.get('prerequisites', [])
                if prereqs:
                    lines += ["**Prerequisites:**"]
                    for p in prereqs:
                        lines += [f"- {p}"]
                    lines += [""]
                walkthrough = exploit_detail.get('walkthrough', [])
                if walkthrough:
                    lines += ["**Exploit Walkthrough:**", ""]
                    for step in walkthrough:
                        lines += [f"**Step {step['step']}: {step['title']}**", ""]
                        lines += [step['detail'], ""]
                        if step.get('code'):
                            lines += [f"```bash", step['code'], f"```", ""]
            # PoC script (if generated)
            poc_detail = f.get("poc_detail")
            if poc_detail:
                lang = poc_detail.get('language', 'python')
                fname = poc_detail.get('filename', 'poc.py')
                script = poc_detail.get('script', '')
                setup = poc_detail.get('setup', [])
                notes = poc_detail.get('notes', '')
                lines += [f"**PoC Script** (`{fname}`)", ""]
                if setup:
                    lines += [f"**Setup:** `{'`, `'.join(setup)}`", ""]
                if notes:
                    lines += [f"**Notes:** {notes}", ""]
                if script:
                    lines += [f"```{lang}", script, "```", ""]
            # Exploit execution (if run)
            exploit_execution = f.get("exploit_execution")
            if exploit_execution:
                verdict = exploit_execution.get('override_verdict') or exploit_execution.get('verdict', 'unknown')
                confidence = exploit_execution.get('confidence', 0.0)
                reasoning = exploit_execution.get('reasoning', '')
                stdout = exploit_execution.get('stdout', '')
                lines += [
                    f"**Live Exploitation Result:**",
                    f"",
                    f"- **Verdict:** {verdict.upper()} ({int(float(confidence) * 100)}%)",
                    f"- **Reasoning:** {reasoning}",
                    "",
                ]
                if stdout:
                    lines += [f"**Output:**", f"```", stdout[:1000], f"```", ""]
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
