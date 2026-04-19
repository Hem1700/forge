# FORGE Plan 13 — PDF Report Generation

**Date:** 2026-04-18  
**Status:** Approved  
**Scope:** Full-engagement PDF report via Playwright server-side rendering of a dedicated React print route, exposed via API endpoint, CLI flag, and UI download button.

---

## Overview

Plan 13 adds professional PDF report export to FORGE. For every engagement, users can generate a complete technical pentest report containing all findings, PoC scripts, weaponized exploit scripts, execution results, LLM verdicts, and override notes. The PDF is generated server-side by Playwright rendering a dedicated `/print/:engagementId` React route — what you see in the print view is exactly what lands in the PDF. The same API endpoint powers both the CLI and the UI download button.

---

## 1. Architecture

```
CLI/UI
  → POST /api/v1/engagements/{id}/report/pdf
      → Playwright navigates to http://{frontend_url}/print/{id}
          → React /print route fetches full engagement + all findings
              (findings include poc_detail, exploit_script, exploit_execution)
          → Playwright waits for networkidle, exports PDF bytes
      → Stream PDF as application/pdf response
  → CLI saves to ./forge_report_{id}.pdf
  → UI triggers browser download via blob URL
```

**Frontend URL config:** New `settings.frontend_url` env var (default: `http://localhost:5173`) tells the backend where the frontend is served. In production, set to the static-served frontend URL.

---

## 2. `/print` React Route

**File:** `frontend/src/pages/PrintReport.tsx`  
**Route:** `/print/:engagementId`

Fetches the full engagement and all findings (with `poc_detail`, `exploit_script`, `exploit_execution`) and renders a print-optimized layout. No navbar, no sidebar, no interactive elements, no syntax highlighting colors.

### Page structure

```
┌─────────────────────────────────────┐
│  FORGE PENTEST REPORT               │
│  Engagement: target.com             │
│  Generated: 2026-04-18              │
│  Total Findings: 12 (3 Critical,    │
│    4 High, 3 Medium, 2 Low)         │
├─────────────────────────────────────┤
│  FINDING 1 — SQL Injection [HIGH]   │
│  Surface: /api/users                │
│  Description: ...                   │
│  Evidence: ...                      │
│  Reproduction Steps: ...            │
│                                     │
│  PoC Script [python]                │
│  ┌─────────────────────────────┐    │
│  │ #!/usr/bin/env python3 ...  │    │
│  └─────────────────────────────┘    │
│                                     │
│  Exploit Script [python]            │
│  ┌─────────────────────────────┐    │
│  └─────────────────────────────┘    │
│                                     │
│  Execution Result                   │
│  Verdict: ✅ CONFIRMED (94%)        │
│  Reasoning: ...                     │
│  stdout: ...                        │
├─────────────────────────────────────┤
│  FINDING 2 — XSS [MEDIUM]          │
│  ...                                │
└─────────────────────────────────────┘
```

### CSS print rules
- `page-break-before: always` on each finding except the first
- Code blocks: monospace, black-on-white, no color syntax highlighting
- Sections with no data (no PoC, no exploit, no execution) omitted entirely
- Print-specific stylesheet applied via `@media print` and always-on styles for the `/print` route

### Data fetching
- Fetches `GET /api/v1/engagements/{id}` for engagement metadata
- Fetches `GET /api/v1/engagements/{id}/findings` for all findings (existing endpoints)
- Renders loading state while fetching; Playwright waits for `networkidle` so data is always present in the PDF

---

## 3. Backend PDF Endpoint

**File:** `backend/app/api/engagements.py` (extend existing router)

```
POST /api/v1/engagements/{engagement_id}/report/pdf
```

### Flow
1. Verify engagement exists — return 404 if not found
2. Launch `playwright.async_api.async_playwright()`, open Chromium
3. Navigate to `{settings.frontend_url}/print/{engagement_id}`
4. Wait for `networkidle`
5. Export: `await page.pdf(format="A4", print_background=True)`
6. Close browser unconditionally (in `finally`)
7. Return `Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=forge_report_{engagement_id}.pdf"})`

### Settings
New field in `backend/app/config.py`:
```python
frontend_url: str = "http://localhost:5173"
```

### Dependency
`playwright==1.44.0` added to `backend/requirements.txt`.  
Chromium installed via `playwright install chromium` (one-time setup, documented in README).

---

## 4. CLI

**File:** `cli/forge_cli/main.py` (extend existing `forge report` command)

New `--pdf` flag on `forge report`:

```bash
forge report <engagement-id> --pdf
```

- Calls `POST /api/v1/engagements/{id}/report/pdf`
- Streams response bytes to `./forge_report_{id}.pdf`
- Prints: `Saved to: ./forge_report_{engagement_id}.pdf`
- Without `--pdf`: existing markdown output unchanged

```
$ forge report eng-abc123 --pdf

  Generating PDF report...
  Saved to: ./forge_report_eng-abc123.pdf
```

---

## 5. Frontend UI

**File:** `frontend/src/pages/Engagement.tsx` (extend existing page)

New "Download PDF" button in the Engagement page header.

### Behavior
- On click: `POST /api/v1/engagements/{id}/report/pdf` → receive blob → trigger browser download via temporary `<a href=URL.createObjectURL(blob)>` 
- While generating: button shows loading spinner, disabled
- On error: toast notification "Failed to generate report"

### New API method
Added to `frontend/src/api/engagements.ts` (new file, or extend existing):
```typescript
downloadPdfReport: (engagementId: string) =>
  fetch(`/api/v1/engagements/${engagementId}/report/pdf`, { method: 'POST' })
    .then(res => res.blob())
```

### New route registration
`/print/:engagementId` added to `frontend/src/main.tsx` (or router config), pointing to `PrintReport`.

---

## 6. Testing

**Backend unit tests (`backend/tests/test_pdf_report.py`):**
- Mock `playwright.async_api.async_playwright` — assert endpoint returns `application/pdf` content-type
- Assert `Content-Disposition` header contains correct filename
- Assert 404 on unknown engagement ID

**Print route — manual verification:**
Navigate to `/print/<id>` in the browser before running PDF export. No automated tests for the React print layout.

**CI skip:**
`PLAYWRIGHT_SKIP=1` env var skips Playwright-dependent tests — same pattern as existing PostgreSQL-dependent integration tests.

---

## 7. File Checklist

| File | Change |
|------|--------|
| `frontend/src/pages/PrintReport.tsx` | New — print-optimized engagement layout |
| `frontend/src/main.tsx` | Add `/print/:engagementId` route |
| `frontend/src/api/engagements.ts` | Add `downloadPdfReport` method |
| `frontend/src/pages/Engagement.tsx` | Add "Download PDF" button |
| `backend/app/api/engagements.py` | Add `POST /{id}/report/pdf` endpoint |
| `backend/app/config.py` | Add `frontend_url` setting |
| `backend/requirements.txt` | Add `playwright==1.44.0` |
| `backend/tests/test_pdf_report.py` | New — unit tests (mocked Playwright) |
| `cli/forge_cli/main.py` | Add `--pdf` flag to `forge report` |

---

## 8. Out of Scope (Plan 13)

- Scheduled report generation
- Email delivery of reports
- Report templates / branding customization
- Multiple export formats (DOCX, HTML)
- Findings filtered by severity in the report
- Cover page / table of contents
