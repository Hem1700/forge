"""Rich display helpers."""
from __future__ import annotations
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "blue",
    "info": "dim",
}

STATUS_COLORS = {
    "pending": "dim",
    "running": "green",
    "paused_at_gate": "yellow",
    "complete": "bold green",
    "aborted": "red",
}

TARGET_ICONS = {
    "web": "🌐",
    "local_codebase": "📁",
    "binary": "⚙️",
}

EVENT_COLORS = {
    "agent_started": "cyan",
    "agent_completed": "green",
    "finding_discovered": "bold yellow",
    "gate_triggered": "bold magenta",
    "campaign_complete": "bold green",
}


def engagement_table(engagements: list[dict]) -> Table:
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold orange1")
    t.add_column("ID", style="dim", width=12)
    t.add_column("Type", width=10)
    t.add_column("Target")
    t.add_column("Status", width=14)
    t.add_column("Gate", width=8)
    t.add_column("Created", width=20)
    t.add_column("Findings", justify="right", width=9)

    for e in engagements:
        eid = e["id"][:8] + "…"
        ttype = e.get("target_type", "web")
        icon = TARGET_ICONS.get(ttype, "")
        target = e.get("target_path") or e.get("target_url", "")
        if len(target) > 40:
            target = "…" + target[-38:]
        status = e.get("status", "")
        scolor = STATUS_COLORS.get(status, "")
        gate = e.get("gate_status", "")
        created = _fmt_dt(e.get("created_at", ""))
        findings = str(e.get("findings_count", ""))
        t.add_row(eid, f"{icon} {ttype}", target, Text(status, style=scolor), gate, created, findings)
    return t


def findings_table(findings: list[dict]) -> Table:
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold orange1", show_lines=True)
    t.add_column("#", width=4, justify="right")
    t.add_column("Severity", width=10)
    t.add_column("Vulnerability", width=28)
    t.add_column("Location", width=30)
    t.add_column("Description")

    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "info")
        scolor = SEVERITY_COLORS.get(sev, "")
        vuln = f.get("vulnerability_class", f.get("title", ""))[:26]
        loc = f.get("affected_surface", f.get("endpoint", ""))
        if len(loc) > 28:
            loc = "…" + loc[-27:]
        desc = f.get("description", "")[:120]
        t.add_row(
            str(i),
            Text(sev.upper(), style=scolor),
            vuln,
            Text(loc, style="dim"),
            desc,
        )
    return t


def severity_summary(findings: list[dict]) -> Panel:
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1

    lines = Text()
    for sev, count in counts.items():
        if count:
            color = SEVERITY_COLORS[sev]
            bar = "█" * min(count, 30)
            lines.append(f"  {sev.upper():10}", style=color)
            lines.append(f" {bar} ", style=color)
            lines.append(f"{count}\n", style="bold")

    lines.append(f"\n  Total: {len(findings)} findings", style="bold white")
    return Panel(lines, title="[bold]Findings Summary[/bold]", border_style="orange1")


def format_event(event: dict) -> Text:
    etype = event.get("type", "")
    payload = event.get("payload", {})
    ts = event.get("timestamp", "")
    if ts:
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
        except Exception:
            pass

    color = EVENT_COLORS.get(etype, "white")
    t = Text()
    t.append(f"[{ts}] ", style="dim")
    t.append(f"{etype}", style=f"bold {color}")

    if etype == "agent_started":
        phase = payload.get("phase") or payload.get("agent_type") or payload.get("agent_id", "")
        t.append(f" → {phase}", style="cyan")
    elif etype == "agent_completed":
        phase = payload.get("phase") or payload.get("agent_type", "")
        n = payload.get("findings_count") or payload.get("hypotheses") or payload.get("attack_surfaces", "")
        t.append(f" ✓ {phase}", style="green")
        if n:
            t.append(f" ({n})", style="dim")
    elif etype == "finding_discovered":
        f = payload.get("finding", {})
        sev = f.get("severity", "")
        vuln = f.get("vulnerability", f.get("vulnerability_class", ""))[:40]
        t.append(f" 🔍 [{sev.upper()}] {vuln}", style=SEVERITY_COLORS.get(sev, "yellow"))
    elif etype == "campaign_complete":
        status = payload.get("status", "")
        if status == "error":
            t.append(f" ✗ {payload.get('error', '')[:80]}", style="red")
        else:
            t.append(" ✓ done", style="bold green")

    return t


def _fmt_dt(s: str) -> str:
    if not s:
        return ""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:16]


import re as _re


def mermaid_to_ascii(source: str) -> str:
    """Parse Mermaid graph LR syntax into ASCII arrow lines."""
    lines = []
    for line in source.split('\n'):
        line = line.strip()
        # Match: NodeA -->|label| NodeB  OR  NodeA --> NodeB
        m = _re.match(r'(\w+)\s*-->\|?"?([^|"]*)"?\|?\s*(\w+)', line)
        if m:
            src = m.group(1).strip()
            label = m.group(2).strip()
            dst = m.group(3).strip()
            if label:
                lines.append(f"  {src} ──[{label}]──► {dst}")
            else:
                lines.append(f"  {src} ──────────► {dst}")
    return '\n'.join(lines) if lines else "  (no path data)"


def render_exploit(finding: dict, exploit: dict) -> None:
    """Print a Rich-formatted exploit report to the console."""
    from rich.panel import Panel as _Panel
    from rich.rule import Rule
    from rich.syntax import Syntax

    sev = finding.get('severity', 'info').upper()
    vuln = finding.get('vulnerability_class') or finding.get('title', 'Finding')
    location = finding.get('affected_surface', '')
    confidence = finding.get('confidence_score', 0)
    difficulty = exploit.get('difficulty', 'unknown')

    diff_color = {'easy': 'red', 'medium': 'yellow', 'hard': 'green'}.get(difficulty, 'white')

    console.print(_Panel(
        f"[bold orange1]Severity:[/bold orange1]    {sev}\n"
        f"[bold orange1]Location:[/bold orange1]    [cyan]{location}[/cyan]\n"
        f"[bold orange1]Confidence:[/bold orange1]  {int(float(confidence) * 100)}%\n"
        f"[bold orange1]Difficulty:[/bold orange1]  [{diff_color}]{difficulty}[/{diff_color}]",
        title=f"[bold]{vuln}[/bold]",
        border_style="orange1",
    ))

    # Walkthrough
    console.print(Rule("[bold orange1]EXPLOIT WALKTHROUGH[/bold orange1]"))
    for step in exploit.get('walkthrough', []):
        console.print(f"\n[bold]Step {step['step']} · {step['title']}[/bold]")
        console.print(f"  {step['detail']}")
        if step.get('code'):
            console.print(Syntax(step['code'], "bash", theme="monokai", padding=(0, 2)))

    # Impact
    console.print(Rule("[bold orange1]IMPACT[/bold orange1]"))
    console.print(f"  {exploit.get('impact', '')}\n")

    # Prerequisites
    prereqs = exploit.get('prerequisites', [])
    if prereqs:
        console.print(Rule("[bold orange1]PREREQUISITES[/bold orange1]"))
        for p in prereqs:
            console.print(f"  [dim]•[/dim] {p}")
        console.print()

    # Attack path
    mermaid_src = exploit.get('attack_path_mermaid', '')
    if mermaid_src:
        console.print(Rule("[bold orange1]ATTACK PATH[/bold orange1]"))
        console.print(mermaid_to_ascii(mermaid_src))
        console.print()
