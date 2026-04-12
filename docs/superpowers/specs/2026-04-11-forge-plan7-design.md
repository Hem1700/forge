# FORGE Plan 7 — Exploit Engine + Finding Detail Page

**Date:** 2026-04-11
**Status:** Approved
**Scope:** Exploit walkthrough generation, attack path visualization, dedicated finding detail page, CLI exploit commands

---

## Overview

Plan 7 adds per-finding exploit intelligence to FORGE. For every vulnerability discovered, users can generate a step-by-step exploit walkthrough, a visual attack path diagram (Mermaid in UI, ASCII in CLI), and a difficulty/impact assessment. This is available in both the React dashboard (dedicated finding page) and the CLI (`forge exploit`).

---

## 1. ExploitEngine (new brain component)

**File:** `backend/app/brain/exploit_engine.py`

Single LLM call (claude-sonnet-4-6) that takes a finding + engagement context and returns structured exploit intelligence.

### Input
```python
finding: dict  # vulnerability_class, affected_surface, description, evidence, severity
context: dict  # target_url/target_path, target_type, app_type from semantic_model
```

### Output schema
```json
{
  "walkthrough": [
    {
      "step": 1,
      "title": "Identify the surface",
      "detail": "Narrative description of this step",
      "code": "curl https://target.com/api/users?id=1' OR '1'='1"
    }
  ],
  "attack_path_mermaid": "graph LR\n  Attacker -->|crafted request| WebServer\n  WebServer -->|unparameterized query| DB\n  DB -->|all rows| Attacker",
  "impact": "Attacker reads all user records without authentication",
  "prerequisites": ["Network access to target", "Knowledge of endpoint path"],
  "difficulty": "easy"
}
```

### Design decisions
- **On-demand generation** — exploit_detail is generated when a user explicitly requests it (UI button or CLI command), not at scan time. Avoids pipeline latency and unnecessary LLM cost for findings nobody views.
- **Cached after first generation** — if `exploit_detail` is already set on the Finding, the endpoint returns it immediately without a new LLM call.
- **Mermaid for attack path** — LLM generates Mermaid `graph LR` syntax directly. Renders as SVG in the browser via the `mermaid` npm package. Parsed into ASCII arrows for CLI rendering.
- Uses the same `_LLMWrapper` pattern as other brain components for testability.

---

## 2. Data Model

**File:** `backend/app/models/finding.py`

One new column added to the `findings` table:

```python
exploit_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

Stores the full ExploitEngine output. Nullable — `None` means not yet generated.

**Migration:** new Alembic migration adding `exploit_detail` JSON column to `findings`.

---

## 3. API

**File:** `backend/app/api/findings.py` (new router)

Registered at prefix `/api/v1/findings` in `main.py`.

### Endpoints

#### `GET /api/v1/findings/{finding_id}`
Returns full finding row including `exploit_detail` (may be null).

Response: full `Finding` dict with all fields.

#### `POST /api/v1/findings/{finding_id}/exploit`
Generate (or return cached) exploit detail.

- If `finding.exploit_detail` is not null: return it immediately, no LLM call.
- If null: call `ExploitEngine.generate(finding, engagement_context)`, persist result to DB, return it.
- Returns 404 if finding not found.
- Response is synchronous — waits for LLM generation to complete before returning (typically 3–8s).

---

## 4. Frontend

### 4a. New route and page

**Route:** `/engagements/:engagementId/findings/:findingId`
**File:** `frontend/src/pages/FindingDetail.tsx`

Layout (two-column on desktop, stacked on mobile):

```
┌─────────────────────────────────────────────────────┐
│ ← Back to Engagement    [CRITICAL] SQL Injection     │
│ Location: /api/users  ·  Confidence: 87%             │
├──────────────────────┬──────────────────────────────┤
│  EXPLOIT WALKTHROUGH │  ATTACK PATH DIAGRAM         │
│  Step 1 ...          │  [Mermaid SVG]               │
│  Step 2 ...          │                              │
│  > curl snippet      │  Impact / Prerequisites /    │
│                      │  Difficulty                  │
├──────────────────────┴──────────────────────────────┤
│  EVIDENCE            │  REMEDIATION                 │
└──────────────────────┴──────────────────────────────┘
```

**Interactions:**
- Static finding fields (severity, location, description, evidence) render immediately on page load from `GET /api/v1/findings/:id`.
- Walkthrough + diagram section shows a **"Generate Exploit"** button if `exploit_detail` is null.
- Clicking the button calls `POST /api/v1/findings/:id/exploit` with a loading spinner.
- If `exploit_detail` is already set, the section renders immediately — no button shown.

### 4b. New components

**`frontend/src/components/ExploitWalkthrough.tsx`**
Renders the numbered step list. Each step shows title, detail paragraph, and an optional code block (monospace, copyable).

**`frontend/src/components/AttackPathDiagram.tsx`**
Wraps the `mermaid` npm package. Accepts `mermaid_source: string`, renders as inline SVG. Shows a skeleton loader while mermaid initializes.

### 4c. FindingsPanel update

Finding rows in `FindingsPanel.tsx` become clickable links (`<Link to={...}>`) navigating to `/engagements/:id/findings/:fid`.

### 4d. Types

Added to `frontend/src/types/index.ts`:

```typescript
export interface ExploitStep {
  step: number
  title: string
  detail: string
  code?: string
}

export interface ExploitDetail {
  walkthrough: ExploitStep[]
  attack_path_mermaid: string
  impact: string
  prerequisites: string[]
  difficulty: 'easy' | 'medium' | 'hard'
}

export interface FindingDetail extends Finding {
  exploit_detail?: ExploitDetail
}
```

### 4e. API client

New file `frontend/src/api/findings.ts` (keeps findings concerns separate from engagements client):

```typescript
export const findingsApi = {
  get: (findingId: string) =>
    apiFetch<FindingDetail>(`/api/v1/findings/${findingId}`),
  generateExploit: (findingId: string) =>
    apiFetch<ExploitDetail>(`/api/v1/findings/${findingId}/exploit`, { method: 'POST' }),
}
```

---

## 5. CLI

### 5a. `forge exploit <finding-id>`

New command in `cli/forge_cli/main.py`. Calls `POST /api/v1/findings/:id/exploit`, then renders with Rich:

```
  [CRITICAL] SQL Injection — /api/users
  Difficulty: easy  ·  Confidence: 87%

  EXPLOIT WALKTHROUGH
  ───────────────────
  Step 1 · Identify the surface
    The /api/users endpoint accepts an unsanitized `id` parameter...

    $ curl "https://target.com/api/users?id=1' OR '1'='1"

  IMPACT
    Attacker reads all user records without authentication.

  PREREQUISITES
    • Network access to target
    • Knowledge of endpoint

  ATTACK PATH
    Attacker ──[crafted request]──► WebServer
    WebServer ──[unparameterized query]──► Database
    Database ──[all rows]──► Attacker
```

Attack path is parsed from Mermaid `graph LR` syntax into ASCII arrows (simple regex parse of `-->` edges with optional `|label|`).

### 5b. `forge findings <engagement-id> --exploit`

Adds `--exploit` flag to the existing `findings` command. After printing the findings table, generates and prints exploit walkthroughs for each finding sequentially.

### 5c. `forge findings <engagement-id> --output report.md`

When `exploit_detail` is available on a finding, the markdown output includes the walkthrough steps and attack path under each finding section.

---

## 6. File Checklist

| File | Change |
|------|--------|
| `backend/app/brain/exploit_engine.py` | New — ExploitEngine class |
| `backend/app/models/finding.py` | Add `exploit_detail` column |
| `backend/app/api/findings.py` | New — GET finding + POST exploit endpoints |
| `backend/app/main.py` | Register findings router |
| `alembic/versions/xxxx_add_exploit_detail.py` | New migration |
| `frontend/src/pages/FindingDetail.tsx` | New page |
| `frontend/src/components/ExploitWalkthrough.tsx` | New component |
| `frontend/src/components/AttackPathDiagram.tsx` | New component (wraps mermaid) |
| `frontend/src/components/FindingsPanel.tsx` | Make rows clickable links |
| `frontend/src/App.tsx` | Add `/engagements/:id/findings/:fid` route |
| `frontend/src/types/index.ts` | Add ExploitStep, ExploitDetail, FindingDetail |
| `frontend/src/api/findings.ts` | New — getFinding, generateExploit |
| `cli/forge_cli/main.py` | Add `forge exploit` command + `--exploit` flag |
| `cli/forge_cli/display.py` | Add exploit rendering helpers |

---

## 7. Out of Scope (Plan 7)

- Authenticated web pipeline (Plan 8)
- Adversarial Validator wiring (Plan 8)
- PDF/Markdown server-side report generation (Plan 9)
- Finding deduplication
- Re-run / incremental scan support
