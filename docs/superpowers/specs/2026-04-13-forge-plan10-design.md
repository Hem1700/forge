# FORGE Plan 10 — PoCEngine + PoC Script Generation

**Date:** 2026-04-13
**Status:** Approved
**Scope:** Per-finding runnable PoC script generation, exploit sequence diagram, CLI `forge poc`, UI download button

---

## Overview

Plan 10 adds a dedicated PoC (Proof-of-Concept) generation layer to FORGE. For every finding, users can generate a detailed, runnable exploit script auto-selected by vulnerability type (Python, bash, or Python+pwntools), plus a Mermaid `sequenceDiagram` showing the request/response flow of the attack. This is available in both the React dashboard (on the FindingDetail page) and the CLI (`forge poc`).

This is distinct from Plan 7's ExploitEngine — Plan 7 generates a narrative walkthrough and a static `graph LR` attack path. Plan 10 generates actual runnable code and a temporal sequence diagram showing how the exploit unfolds over time.

---

## 1. PoCEngine (new brain component)

**File:** `backend/app/brain/poc_engine.py`

Single LLM call (claude-sonnet-4-6) that takes a finding + engagement context and returns structured PoC data.

### Input
```python
finding: dict  # vulnerability_class, affected_surface, description, evidence, severity
context: dict  # target_url/target_path, target_type, app_type from semantic_model
```

### Output schema
```json
{
  "language": "python",
  "filename": "poc_sqli_api_users.py",
  "script": "#!/usr/bin/env python3\nimport requests\n\nTARGET_URL = 'https://target.com'\n\n...",
  "setup": ["pip install requests"],
  "notes": "Replace TARGET_URL with the actual target before running.",
  "sequence_diagram": "sequenceDiagram\n  participant Attacker\n  participant Server\n  Attacker->>Server: GET /api/users?id=1' OR '1'='1\n  Server-->>Attacker: 200 OK — all rows returned"
}
```

### Language selection rules (baked into system prompt)
| Vulnerability class | Language |
|---|---|
| sqli, xss, ssrf, auth_bypass, idor, open_redirect | Python (`requests`) |
| cmdi, path_traversal (simple HTTP) | bash/curl |
| buffer_overflow, format_string, use_after_free, rop | Python + `pwntools` |
| default / unknown | Python (`requests`) |

### Design decisions
- **On-demand generation** — `poc_detail` is generated when explicitly requested (UI button or CLI command), not at scan time.
- **Cached after first generation** — if `poc_detail` is already set on the Finding, the endpoint returns it immediately without a new LLM call.
- **`sequenceDiagram` not `graph LR`** — Mermaid sequence diagrams show temporal request/response flow, which is visually and semantically distinct from Plan 7's static attack path graph.
- **Detailed, target-specific scripts** — the system prompt instructs the LLM to use the actual target URL/path from context, real parameter names from evidence, and realistic payloads. Not generic templates.
- **`setup` array** — dependencies needed to run the script (e.g. `pip install requests pwntools`). May be empty for bash scripts.
- Same `_LLMWrapper` pattern as `ExploitEngine` for testability.

---

## 2. Data Model

**File:** `backend/app/models/finding.py`

One new column added to the `findings` table:

```python
poc_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

`None` = not yet generated. Stores the full PoCEngine output.

**Migration:** new Alembic migration adding `poc_detail` JSON column to `findings`.

---

## 3. API

**File:** `backend/app/api/findings.py` (extend existing router)

Two new endpoints added to the existing `/api/v1/findings` router.

#### `GET /api/v1/findings/{finding_id}/poc`
Returns `poc_detail` for a finding (may be null). Useful for the UI to check generation status without triggering generation.

Response:
```json
{ "poc_detail": { ... } | null }
```

Returns 404 if finding not found.

#### `POST /api/v1/findings/{finding_id}/poc`
Generate (or return cached) PoC.

- If `finding.poc_detail` is not null: return it immediately, no LLM call.
- If null: call `PoCEngine.generate(finding, engagement_context)`, persist result to DB, return it.
- Returns 404 if finding not found.
- Response is synchronous — waits for LLM generation (~5–15s).

---

## 4. Frontend

### 4a. New types

Added to `frontend/src/types/index.ts`:

```typescript
export interface PoCDetail {
  language: string
  filename: string
  script: string
  setup: string[]
  notes: string
  sequence_diagram: string
}
```

`FindingDetail` extended:
```typescript
export interface FindingDetail extends Finding {
  exploit_detail?: ExploitDetail | null
  poc_detail?: PoCDetail | null
  reproduction_steps?: string[]
  validation_status?: string
}
```

### 4b. New API method

Added to `frontend/src/api/findings.ts`:
```typescript
generatePoC: (findingId: string) =>
  apiFetch<PoCDetail>(`/api/v1/findings/${findingId}/poc`, { method: 'POST' })
```

### 4c. New components

**`frontend/src/components/PoCScript.tsx`**

Renders the generated PoC script:
- Language badge (e.g. `python`, `bash`) top-left of the code block
- Syntax-highlighted monospace code block (same style as ExploitWalkthrough code blocks)
- **Copy** button — clipboard API
- **Download** button — triggers browser file download using `poc_detail.filename`
- Setup instructions shown below the script if `setup` array is non-empty
- Notes shown in muted text if `notes` is non-empty

**`frontend/src/components/ExploitSequenceDiagram.tsx`**

Wraps the `mermaid` npm package (already installed). Accepts `source: string`, renders `sequenceDiagram` syntax as inline SVG. Same dark theme, skeleton loader, and error fallback pattern as `AttackPathDiagram`.

### 4d. FindingDetail page update

**File:** `frontend/src/pages/FindingDetail.tsx`

A new "PoC Script" section added below the existing "Exploit Intelligence" section:

```
┌─────────────────────────────────────────────────────┐
│  EXPLOIT INTELLIGENCE  (existing Plan 7 section)     │
├──────────────────────────────────────────────────────┤
│  PoC SCRIPT                                          │
│  ┌─────────────────────┐  ┌────────────────────────┐ │
│  │ [python] script...  │  │ sequenceDiagram SVG    │ │
│  │ [Copy] [Download]   │  │                        │ │
│  │ Setup: pip install  │  │                        │ │
│  │ Notes: ...          │  │                        │ │
│  └─────────────────────┘  └────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

- If `poc_detail` is null: shows **"Generate PoC"** button with loading spinner (same UX pattern as "Generate Exploit")
- If set: renders `PoCScript` left, `ExploitSequenceDiagram` right
- Error state shown inline if generation fails

---

## 5. CLI

### 5a. `forge poc <finding-id>`

New command in `cli/forge_cli/main.py`:

```
  [HIGH] SQL Injection — /api/users
  Language: python  ·  File: poc_sqli_api_users.py

  POC SCRIPT
  ──────────────────
  #!/usr/bin/env python3
  import requests
  ...

  SETUP
    • pip install requests

  NOTES
    Replace TARGET_URL with the actual target before running.

  SEQUENCE
    Attacker ->> Server: GET /api/users?id=1' OR '1'='1
    Server -->> Attacker: 200 OK — all rows returned

  Saved to: ./poc_sqli_api_users.py
```

- Calls `POST /api/v1/findings/:id/poc` with 120s timeout
- Prints script with Rich `Syntax` highlighting
- Writes file to current working directory using `poc_detail.filename`
- Parses `sequenceDiagram` syntax into ASCII arrows via `sequence_to_ascii()` helper

### 5b. `forge findings <id> --poc`

Adds `--poc` flag to the existing `findings` command. After printing the findings table, generates and prints PoC for each finding sequentially (same pattern as `--exploit`). Only fires when not `--json` or `--output`.

### 5c. `forge report` update

When `poc_detail` is present on a finding, the markdown output includes the script in a fenced code block under each finding section:

````markdown
**PoC Script** (`poc_sqli_api_users.py`)

```python
#!/usr/bin/env python3
...
```

**Setup:** `pip install requests`
**Notes:** Replace TARGET_URL with the actual target before running.
````

### 5d. New display helpers

Added to `cli/forge_cli/display.py`:
- `sequence_to_ascii(source: str) -> str` — parses Mermaid `sequenceDiagram` lines into readable ASCII arrows (e.g. `Attacker ->> Server: label` → `  Attacker ──[label]──► Server`)
- `render_poc(finding: dict, poc: dict) -> None` — Rich-formatted PoC output with Panel header, Syntax script block, setup/notes, and sequence ASCII

---

## 6. File Checklist

| File | Change |
|------|--------|
| `backend/app/brain/poc_engine.py` | New — PoCEngine class |
| `backend/app/models/finding.py` | Add `poc_detail` column |
| `backend/alembic/versions/XXXX_add_poc_detail.py` | New migration |
| `backend/app/api/findings.py` | Add GET poc + POST poc endpoints |
| `backend/tests/test_poc_engine.py` | New — unit tests (mocked LLM) |
| `backend/tests/test_api_findings.py` | Extend — add poc endpoint tests |
| `frontend/src/types/index.ts` | Add PoCDetail, extend FindingDetail |
| `frontend/src/api/findings.ts` | Add generatePoC method |
| `frontend/src/components/PoCScript.tsx` | New — script viewer with copy/download |
| `frontend/src/components/ExploitSequenceDiagram.tsx` | New — mermaid sequenceDiagram renderer |
| `frontend/src/pages/FindingDetail.tsx` | Add PoC section below exploit section |
| `cli/forge_cli/display.py` | Add sequence_to_ascii + render_poc |
| `cli/forge_cli/main.py` | Add forge poc command + --poc flag + report update |

---

## 7. Out of Scope (Plan 10)

- Authenticated web pipeline (Plan 8)
- Server-side PDF report generation (Plan 9)
- Chained exploit scripts (multiple findings combined into one attack chain)
- Automated PoC execution / sandboxed running of generated scripts
- CVE-mapped PoC lookup (pulling existing public exploits)
