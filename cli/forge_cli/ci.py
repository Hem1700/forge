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
        label = "**Top findings:**" if any(
            f.get("severity") in ("critical", "high") for f in top
        ) else "**All findings (none critical/high):**"
        lines += [
            "",
            label,
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
    """Post a PR comment (if pr is not None) or a commit comment."""
    if pr is not None:
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
