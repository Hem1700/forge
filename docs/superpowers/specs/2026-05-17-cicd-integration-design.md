# CI/CD Integration Design

**Date:** 2026-05-17  
**Status:** Approved

---

## Goal

Allow any CI/CD pipeline to trigger a FORGE security scan and gate on findings severity — with native GitHub feedback (commit status check + commit/PR comment) and a generic JSON callback for non-GitHub CI systems.

---

## Approach

CLI-first (pull model). The CI runner calls `forge ci scan <target>`, which:

1. Creates and starts an engagement via the existing REST API
2. Polls until the engagement finishes
3. Posts results back to GitHub (commit status + comment) if credentials are present
4. POSTs findings JSON to a callback URL if `--callback-url` is set
5. Exits non-zero if findings at/above the configured severity threshold exist

No new backend endpoints or database changes are required. All GitHub API calls use `urllib` (already in the CLI) — no new dependencies.

---

## Command Surface

### `forge ci scan <target>`

One-command CI scan. Wraps create → start → wait → report.

```
forge ci scan <target> [OPTIONS]

Arguments:
  target    URL (web) or filesystem path (local_codebase / binary)

Options:
  --type            web | local_codebase | binary  (auto-detected from target)
  --fail-on         critical | high | medium | low | none  (default: high)
                    Exit 1 if any finding at this severity or above exists.
                    Use "none" for informational scans that must not block CI.
  --timeout         Max seconds to wait for completion  (default: 1800)
  --poll-interval   Seconds between status checks  (default: 15)

  GitHub feedback (all default to env vars):
  --github-token    GitHub PAT or GITHUB_TOKEN env var
  --repo            owner/repo  (default: GITHUB_REPOSITORY)
  --commit          Commit SHA  (default: GITHUB_SHA)
  --pr              PR number for PR comment  (optional; falls back to commit comment)

  Generic CI:
  --callback-url    POST findings JSON to this URL on completion

  Standard:
  --api-url         Override FORGE_API_URL
  --api-key         Override FORGE_API_KEY
```

**Exit codes:**
- `0` — scan completed, no findings at/above threshold (or `--fail-on none`)
- `1` — findings at/above threshold exist, OR engagement aborted/errored

**Stdout:** Rich-formatted findings summary (same as `forge findings <id>`), followed by a one-liner: `✓ Clean — no high+ findings` or `✗ 2 high, 1 critical findings found`.

### `forge ci report <engagement-id>`

Post results for an already-finished engagement. Accepts the same `--github-token / --repo / --commit / --pr / --callback-url` options. Exits 0 always (reporting only).

---

## GitHub Feedback

When `--github-token` and `--repo` and `--commit` are present, two GitHub API calls are made (both via `urllib`, no extra deps):

### Commit status check

`POST /repos/{owner}/{repo}/statuses/{sha}`

```json
{
  "state": "success" | "failure",
  "description": "0 critical · 2 high · 3 medium",
  "context": "forge / security-scan",
  "target_url": "<FORGE_API_URL>/engagements/<id>"
}
```

`state` is `failure` if any finding exists at/above `--fail-on` threshold; `success` otherwise.

### Comment

- If `--pr` is set: `POST /repos/{owner}/{repo}/issues/{pr}/comments`
- Otherwise: `POST /repos/{owner}/{repo}/commits/{sha}/comments`

Comment body is a markdown summary (~30 lines):

```markdown
## FORGE Security Scan

| Severity | Count |
|----------|-------|
| Critical | 0     |
| High     | 2     |
| Medium   | 3     |

**Top findings:**

| Severity | Vulnerability | Location |
|----------|--------------|----------|
| HIGH | SQL Injection | /api/users |
| HIGH | XSS | /search |
| MEDIUM | IDOR | /api/items/{id} |

[View full engagement →](http://localhost:8080/engagements/<id>)
```

**Failure policy:** If either GitHub API call fails (network error, bad token, rate limit), `forge ci scan` prints a warning to stderr but continues and exits based on the findings threshold. A reporting failure never masks the security result.

---

## Generic CI Callback

When `--callback-url` is set, on engagement completion FORGE POSTs:

```json
{
  "engagement_id": "<uuid>",
  "status": "complete" | "aborted",
  "target_url": "https://example.com",
  "findings_count": 5,
  "severity_counts": {"critical": 0, "high": 2, "medium": 3, "low": 0, "info": 0},
  "threshold_breached": true,
  "findings": [ ...full findings array... ]
}
```

HTTP POST with `Content-Type: application/json`. Non-2xx response is treated as a warning (logged, not fatal).

---

## GitHub Actions Workflow Template

File: `cli/forge_ci_template.yml`

```yaml
name: FORGE Security Scan
on:
  push:
    branches: [main, master]

jobs:
  forge-scan:
    runs-on: ubuntu-latest
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

Teams copy this file to `.github/workflows/forge-scan.yml` and set three repo variables:
- `TARGET_URL` — the URL or path to scan
- `FORGE_API_URL` — the FORGE backend URL (e.g. `https://forge.yourcompany.com`)
- `FORGE_API_KEY` (secret) — an API key from `forge api-keys create ci`

---

## Files

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `cli/forge_cli/ci.py` | GitHub API calls, markdown formatter, callback poster |
| Create | `cli/forge_cli/commands/ci.py` | Click group: `scan` and `report` commands |
| Modify | `cli/forge_cli/api.py` | Add `wait_for_engagement(eid, timeout, poll_interval)` |
| Modify | `cli/forge_cli/main.py` | Import + `cli.add_command(ci_group)` |
| Create | `cli/forge_ci_template.yml` | Drop-in GitHub Actions workflow |

---

## Data Flow

```
CI runner
  │
  │  forge ci scan https://app.example.com --fail-on high \
  │    --github-token $TOKEN --repo acme/app --commit $SHA
  │
  ▼
forge CLI
  ├── POST /api/v1/engagements/           → {id: <uuid>}
  ├── POST /api/v1/engagements/{id}/start → {status: started}
  │
  │   [poll every 15s]
  ├── GET  /api/v1/engagements/{id}       → {status: running}  ×N
  ├── GET  /api/v1/engagements/{id}       → {status: complete}
  ├── GET  /api/v1/engagements/{id}/findings → [{severity, vuln_class, ...}]
  │
  ├── GitHub API: POST /repos/acme/app/statuses/{sha}  → commit status
  ├── GitHub API: POST /repos/acme/app/commits/{sha}/comments → comment
  │
  └── exit 0 or exit 1 (based on --fail-on threshold)
```

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Backend unreachable | Exit 1 with connection error message |
| Engagement aborted | Exit 1, print abort reason |
| Timeout reached | Exit 1, print "timed out after N seconds", engagement left running |
| GitHub API failure | Print warning to stderr, continue, exit based on findings |
| Callback URL failure | Print warning to stderr, continue |

---

## Testing

- Unit: `ci.py` functions — `format_findings_markdown`, `threshold_breached`, `build_callback_payload`
- Integration: `forge ci scan` end-to-end with a real (test-DB) backend — verify exit code, verify GitHub calls via mock
- Manual smoke: Run against `http://localhost:8080` with a real engagement, check GitHub comment + status appear on a test repo
