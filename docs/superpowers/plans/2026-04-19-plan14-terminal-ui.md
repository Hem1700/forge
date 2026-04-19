# Plan 14: Terminal UI Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign all FORGE frontend pages to a Terminal/Hacker aesthetic — pure black, Cyan (#00d4ff) accent, monospace everywhere, zero rounded corners, process-table home layout.

**Architecture:** Purely visual overhaul. Replace all Tailwind utility classes with inline `style` objects using a shared set of terminal CSS variables. No routing, API, state, or logic changes. All five files touched: `index.css`, `Home.tsx`, `EngagementDashboard.tsx`, `Engagement.tsx`, `SwarmMonitor.tsx`, `FindingsPanel.tsx`, `HumanGate.tsx`, `FindingDetail.tsx`.

**Tech Stack:** React 18, TypeScript, Vite, existing Tailwind install (kept but overridden by body font-family + CSS vars)

---

## File Structure

| File | Change |
|---|---|
| `frontend/src/index.css` | Add CSS variables + global monospace reset |
| `frontend/src/pages/Home.tsx` | Remove Tailwind wrapper, delegate to dashboard |
| `frontend/src/components/EngagementDashboard.tsx` | Full rewrite — process table layout |
| `frontend/src/pages/Engagement.tsx` | Full rewrite — terminal header + 2-col layout |
| `frontend/src/components/SwarmMonitor.tsx` | Full rewrite — terminal event log |
| `frontend/src/components/FindingsPanel.tsx` | Full rewrite — terminal findings table |
| `frontend/src/components/HumanGate.tsx` | Full rewrite — terminal gate bar |
| `frontend/src/pages/FindingDetail.tsx` | Full rewrite — terminal detail page |

---

### Task 1: CSS Foundation

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Replace index.css with terminal globals**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg:            #050505;
  --surface:       #020c10;
  --border:        #0a2530;
  --border-deep:   #05181f;
  --accent:        #00d4ff;
  --accent-dim:    #00d4ff40;
  --accent-bg:     #00d4ff08;
  --accent-glow:   #00d4ff30;
  --text-primary:  #cccccc;
  --text-secondary:#555555;
  --text-dim:      #333333;
  --text-label:    #1a4a5a;

  --running:   #00d4ff;
  --complete:  #22c55e;
  --gate:      #f59e0b;
  --pending:   #555555;
  --aborted:   #ef4444;

  --crit:   #ef4444;
  --high:   #f97316;
  --medium: #f59e0b;
  --low:    #22c55e;
  --info:   #555555;
}

*, *::before, *::after {
  box-sizing: border-box;
  border-radius: 0 !important;
}

html, body, #root {
  background: var(--bg);
  color: var(--text-primary);
  font-family: 'Courier New', Courier, monospace;
  margin: 0;
  min-height: 100vh;
}

* { font-family: inherit; }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: #0a2530; }

input, button, select, textarea { font-family: inherit; }
button { cursor: pointer; }
```

- [ ] **Step 2: Verify TypeScript builds cleanly**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1 | tail -5
```

Expected: no errors, dist output line shown.

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE && git add frontend/src/index.css && git commit -m "style: terminal CSS foundation — variables + global reset"
```

---

### Task 2: Home Page

**Files:**
- Modify: `frontend/src/pages/Home.tsx`

- [ ] **Step 1: Replace Home.tsx**

The Home page now just provides a minimal wrapper — all layout lives in EngagementDashboard.

```tsx
import { useEffect } from 'react'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import { EngagementDashboard } from '../components/EngagementDashboard'

export function Home() {
  const setEngagements = useEngagementStore((s) => s.setEngagements)

  useEffect(() => {
    engagementsApi.list().then(setEngagements).catch(console.error)
  }, [setEngagements])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <EngagementDashboard />
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1 | tail -5
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE && git add frontend/src/pages/Home.tsx && git commit -m "style: Home page — minimal terminal wrapper"
```

---

### Task 3: EngagementDashboard — Process Table

**Files:**
- Modify: `frontend/src/components/EngagementDashboard.tsx`

- [ ] **Step 1: Replace EngagementDashboard.tsx with terminal process table**

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import type { Engagement, EngagementStatus, TargetType } from '../types'

const STATUS: Record<EngagementStatus, { color: string; label: string }> = {
  running:        { color: 'var(--running)', label: '● RUNNING' },
  complete:       { color: 'var(--complete)', label: '✓ COMPLETE' },
  paused_at_gate: { color: 'var(--gate)',    label: '⊘ GATE' },
  pending:        { color: 'var(--pending)', label: '○ PENDING' },
  aborted:        { color: 'var(--aborted)', label: '✕ ABORTED' },
}

const TYPE: Record<TargetType, string> = {
  web: 'web',
  local_codebase: 'code',
  binary: 'binary',
}

const COLS = '110px 1fr 70px 90px 65px 90px'

export function EngagementDashboard() {
  const engagements = useEngagementStore((s) => s.engagements)
  const setEngagements = useEngagementStore((s) => s.setEngagements)
  const upsertEngagement = useEngagementStore((s) => s.upsertEngagement)
  const navigate = useNavigate()

  const [showForm, setShowForm] = useState(false)
  const [targetType, setTargetType] = useState<TargetType>('web')
  const [targetUrl, setTargetUrl] = useState('')
  const [targetPath, setTargetPath] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [starting, setStarting] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const payload: Parameters<typeof engagementsApi.create>[0] = {
        target_url: targetType === 'web' ? targetUrl.trim() : (targetPath.trim() || 'local'),
        target_type: targetType,
        target_path: targetType !== 'web' ? targetPath.trim() : undefined,
      }
      await engagementsApi.create(payload)
      const list = await engagementsApi.list()
      setEngagements(list)
      setTargetUrl('')
      setTargetPath('')
      setShowForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create engagement')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleStart(e: React.MouseEvent, eng: Engagement) {
    e.stopPropagation()
    setStarting(eng.id)
    try {
      await engagementsApi.start(eng.id)
      const updated = await engagementsApi.get(eng.id)
      upsertEngagement(updated)
      navigate(`/engagement/${eng.id}`)
    } catch (err) {
      console.error('Failed to start engagement', err)
    } finally {
      setStarting(null)
    }
  }

  return (
    <div style={{ padding: '20px 24px' }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '12px', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
          <span style={{ color: 'var(--accent)', fontSize: '13px', letterSpacing: '3px', fontWeight: 700 }}>FORGE</span>
          <span style={{ color: 'var(--text-label)', fontSize: '9px', letterSpacing: '1px' }}>v14.0 // offensive security platform</span>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          style={{ background: 'transparent', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: '9px', padding: '3px 12px', letterSpacing: '1px' }}
        >
          {showForm ? '× CANCEL' : '+ NEW'}
        </button>
      </div>

      {/* New engagement form */}
      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{ marginBottom: '16px', padding: '12px', border: '1px solid var(--border)', borderLeft: '2px solid var(--accent)', background: 'var(--surface)' }}
        >
          <div style={{ color: 'var(--text-label)', fontSize: '9px', letterSpacing: '1px', marginBottom: '6px' }}>NEW ENGAGEMENT</div>

          <div style={{ marginBottom: '8px' }}>
            <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>TARGET_TYPE</div>
            <div style={{ display: 'flex', gap: '4px' }}>
              {(['web', 'local_codebase', 'binary'] as TargetType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTargetType(t)}
                  style={{
                    flex: 1, padding: '4px 0', fontSize: '8px', letterSpacing: '1px',
                    background: targetType === t ? 'var(--accent-bg)' : 'transparent',
                    border: `1px solid ${targetType === t ? 'var(--accent)' : 'var(--border)'}`,
                    color: targetType === t ? 'var(--accent)' : 'var(--text-secondary)',
                  }}
                >
                  {TYPE[t].toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {targetType === 'web' ? (
            <div style={{ marginBottom: '8px' }}>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>TARGET_URL</div>
              <input
                type="url"
                required
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                placeholder="https://target.example.com"
                style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: '10px', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
          ) : (
            <div style={{ marginBottom: '8px' }}>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>
                {targetType === 'binary' ? 'BINARY_PATH' : 'CODEBASE_PATH'}
              </div>
              <input
                type="text"
                required
                value={targetPath}
                onChange={(e) => setTargetPath(e.target.value)}
                placeholder={targetType === 'binary' ? '/path/to/binary' : '/Users/you/project'}
                style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: '10px', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
          )}

          {error && <div style={{ color: 'var(--crit)', fontSize: '9px', marginBottom: '6px' }}>{error}</div>}

          <button
            type="submit"
            disabled={submitting}
            style={{ width: '100%', padding: '6px 0', background: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: '9px', letterSpacing: '1px', opacity: submitting ? 0.5 : 1 }}
          >
            {submitting ? 'CREATING...' : '▶ CREATE ENGAGEMENT'}
          </button>
        </form>
      )}

      {/* Table */}
      {engagements.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', color: 'var(--text-label)', fontSize: '9px', letterSpacing: '1px', borderBottom: '1px solid var(--border)', paddingBottom: '4px', marginBottom: '2px' }}>
          <span>STATUS</span>
          <span>TARGET</span>
          <span>TYPE</span>
          <span>FINDINGS</span>
          <span>DATE</span>
          <span></span>
        </div>
      )}

      {engagements.length === 0 ? (
        <div style={{ color: 'var(--text-dim)', fontSize: '9px', padding: '20px 0' }}>
          &gt; no engagements found. press + NEW to begin_
        </div>
      ) : (
        engagements.map((eng) => {
          const st = STATUS[eng.status]
          const label = eng.target_path ?? eng.target_url
          const date = new Date(eng.created_at).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' })
          return (
            <div
              key={eng.id}
              onClick={() => navigate(`/engagement/${eng.id}`)}
              style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-deep)', cursor: 'pointer' }}
            >
              <span style={{ color: st.color, fontSize: '9px', letterSpacing: '1px' }}>{st.label}</span>
              <span style={{ color: 'var(--text-primary)', fontSize: '10px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: '9px' }}>{TYPE[eng.target_type]}</span>
              <span style={{ color: '#aaa', fontSize: '9px' }}>—</span>
              <span style={{ color: 'var(--text-dim)', fontSize: '9px' }}>{date}</span>
              <span>
                {eng.status === 'pending' ? (
                  <button
                    onClick={(e) => handleStart(e, eng)}
                    disabled={starting === eng.id}
                    style={{ background: 'transparent', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: '8px', padding: '2px 8px', letterSpacing: '1px' }}
                  >
                    {starting === eng.id ? '...' : '▶ LAUNCH'}
                  </button>
                ) : (
                  <span style={{ color: 'var(--accent-glow)', fontSize: '8px' }}>[view]</span>
                )}
              </span>
            </div>
          )
        })
      )}

      <div style={{ color: 'var(--accent-glow)', fontSize: '9px', marginTop: '10px' }}>
        {engagements.length} engagement(s) loaded_
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1 | tail -5
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE && git add frontend/src/components/EngagementDashboard.tsx && git commit -m "style: EngagementDashboard — terminal process table"
```

---

### Task 4: Engagement Page

**Files:**
- Modify: `frontend/src/pages/Engagement.tsx`

- [ ] **Step 1: Replace Engagement.tsx with terminal layout**

```tsx
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import { useSwarmStream } from '../hooks/useSwarmStream'
import { SwarmMonitor } from '../components/SwarmMonitor'
import { HumanGate } from '../components/HumanGate'
import { FindingsPanel } from '../components/FindingsPanel'
import { ReportViewer } from '../components/ReportViewer'
import type { EngagementStatus } from '../types'

const STATUS: Record<EngagementStatus, { color: string; label: string }> = {
  running:        { color: 'var(--running)', label: '● RUNNING' },
  complete:       { color: 'var(--complete)', label: '✓ COMPLETE' },
  paused_at_gate: { color: 'var(--gate)',    label: '⊘ GATE' },
  pending:        { color: 'var(--pending)', label: '○ PENDING' },
  aborted:        { color: 'var(--aborted)', label: '✕ ABORTED' },
}

export function Engagement() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const setActiveEngagement = useEngagementStore((s) => s.setActiveEngagement)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)
  const setFindings = useEngagementStore((s) => s.setFindings)
  const [pdfLoading, setPdfLoading] = useState(false)

  useEffect(() => {
    if (!id) return
    engagementsApi.get(id).then(setActiveEngagement).catch(console.error)
    engagementsApi.findings(id).then(setFindings).catch(console.error)
    return () => {
      setActiveEngagement(null)
      setFindings([])
    }
  }, [id, setActiveEngagement, setFindings])

  useSwarmStream(id ?? null)

  async function handleDownloadPdf() {
    if (!activeEngagement) return
    setPdfLoading(true)
    try {
      const blob = await engagementsApi.downloadPdfReport(activeEngagement.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `forge_report_${activeEngagement.id}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 100)
    } catch {
      alert('Failed to generate report')
    } finally {
      setPdfLoading(false)
    }
  }

  if (!activeEngagement) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', letterSpacing: '1px' }}>
        &gt; loading engagement_
      </div>
    )
  }

  const st = STATUS[activeEngagement.status]
  const label = activeEngagement.target_path ?? activeEngagement.target_url

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      {/* Header */}
      <div style={{ borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={() => navigate(-1)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: '9px', letterSpacing: '1px', padding: 0 }}
        >
          ← FORGE
        </button>
        <span style={{ color: 'var(--text-label)', fontSize: '9px' }}>/</span>
        <span style={{ color: 'var(--text-primary)', fontSize: '11px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
        <span style={{ color: st.color, fontSize: '9px', letterSpacing: '1px', border: `1px solid ${st.color}40`, padding: '2px 8px' }}>{st.label}</span>
        <button
          onClick={handleDownloadPdf}
          disabled={pdfLoading}
          style={{ background: 'transparent', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: '9px', padding: '3px 10px', letterSpacing: '1px', opacity: pdfLoading ? 0.5 : 1 }}
        >
          {pdfLoading ? '...' : 'PDF ↓'}
        </button>
      </div>

      {/* Two-column body */}
      <div style={{ padding: '16px 24px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <SwarmMonitor />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <HumanGate engagement={activeEngagement} />
          <FindingsPanel />
        </div>
      </div>

      {/* Report viewer */}
      <div style={{ padding: '0 24px 32px' }}>
        <ReportViewer engagementId={activeEngagement.id} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1 | tail -5
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE && git add frontend/src/pages/Engagement.tsx && git commit -m "style: Engagement page — terminal header + two-column layout"
```

---

### Task 5: SwarmMonitor

**Files:**
- Modify: `frontend/src/components/SwarmMonitor.tsx`

- [ ] **Step 1: Replace SwarmMonitor.tsx with terminal event log**

```tsx
import { useEngagementStore } from '../store/engagement'
import type { SwarmEvent } from '../types'

const EVENT_COLOR: Record<SwarmEvent['type'], string> = {
  agent_started:     'var(--accent)',
  agent_completed:   'var(--complete)',
  finding_discovered:'var(--high)',
  gate_triggered:    'var(--gate)',
  campaign_complete: 'var(--complete)',
  ping:              'var(--text-secondary)',
}

export function SwarmMonitor() {
  const events = useEngagementStore((s) => s.events)
  const agents = useEngagementStore((s) => s.agents)
  const recent = events.slice(0, 30)

  return (
    <div style={{ border: '1px solid var(--border)', borderLeft: '2px solid var(--accent)', background: 'var(--surface)', padding: '12px' }}>
      {/* Panel header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '8px', marginBottom: '8px' }}>
        <span style={{ color: 'var(--accent)', fontSize: '9px', letterSpacing: '2px' }}>SWARM MONITOR</span>
        {agents.length > 0 && (
          <span style={{ color: 'var(--text-label)', fontSize: '9px', border: '1px solid var(--border)', padding: '1px 6px' }}>
            {agents.length} AGENT{agents.length === 1 ? '' : 'S'}
          </span>
        )}
      </div>

      {/* Event log */}
      <div style={{ maxHeight: '440px', overflowY: 'auto' }}>
        {recent.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: '9px', padding: '16px 0' }}>
            &gt; waiting for events_
          </div>
        ) : (
          recent.map((event, idx) => {
            const ts = new Date(event.timestamp).toLocaleTimeString('en-US', { hour12: false })
            return (
              <div key={idx} style={{ borderBottom: '1px solid var(--border-deep)', padding: '4px 0', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--text-dim)', fontSize: '8px', flexShrink: 0, marginTop: '1px' }}>[{ts}]</span>
                <span style={{ color: EVENT_COLOR[event.type], fontSize: '8px', letterSpacing: '1px', flexShrink: 0 }}>{event.type}</span>
                <span style={{ color: 'var(--text-secondary)', fontSize: '8px', wordBreak: 'break-all' }}>
                  {JSON.stringify(event.payload)}
                </span>
              </div>
            )
          })
        )}
      </div>

      {/* Cursor */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '6px', marginTop: '6px', color: 'var(--accent-glow)', fontSize: '9px' }}>
        _
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1 | tail -5
```

Expected: clean build.

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE && git add frontend/src/components/SwarmMonitor.tsx && git commit -m "style: SwarmMonitor — terminal event log"
```

---

### Task 6: FindingsPanel + HumanGate

**Files:**
- Modify: `frontend/src/components/FindingsPanel.tsx`
- Modify: `frontend/src/components/HumanGate.tsx`

- [ ] **Step 1: Replace FindingsPanel.tsx with terminal table**

```tsx
import { Link } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import type { Severity } from '../types'

const SEV_COLOR: Record<Severity, string> = {
  critical: 'var(--crit)',
  high:     'var(--high)',
  medium:   'var(--medium)',
  low:      'var(--low)',
  info:     'var(--info)',
}

const COLS = '65px 1fr 120px 50px'

export function FindingsPanel() {
  const findings = useEngagementStore((s) => s.findings)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)
  const filtered = activeEngagement ? findings.filter((f) => f.engagement_id === activeEngagement.id) : findings

  return (
    <div style={{ border: '1px solid var(--border)', background: 'var(--surface)', padding: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '8px', marginBottom: '8px' }}>
        <span style={{ color: 'var(--accent)', fontSize: '9px', letterSpacing: '2px' }}>FINDINGS</span>
        <span style={{ color: 'var(--text-label)', fontSize: '9px', border: '1px solid var(--border)', padding: '1px 6px' }}>{filtered.length}</span>
      </div>

      {filtered.length === 0 ? (
        <div style={{ color: 'var(--text-secondary)', fontSize: '9px', padding: '12px 0' }}>
          &gt; no findings yet_
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', borderBottom: '1px solid var(--border)', paddingBottom: '4px', marginBottom: '2px' }}>
            <span>SEV</span>
            <span>VULNERABILITY</span>
            <span>LOCATION</span>
            <span>CONF</span>
          </div>
          <div style={{ maxHeight: '360px', overflowY: 'auto' }}>
            {filtered.map((f) => {
              const vulnClass = f.vulnerability_class ?? f.attack_class ?? f.title
              const location = f.affected_surface ?? f.endpoint ?? ''
              return (
                <div key={f.id} style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid var(--border-deep)' }}>
                  <span style={{ color: SEV_COLOR[f.severity], fontSize: '8px', letterSpacing: '1px' }}>[{f.severity.toUpperCase().slice(0, 4)}]</span>
                  <Link
                    to={`/engagement/${f.engagement_id}/findings/${f.id}`}
                    style={{ color: 'var(--text-primary)', fontSize: '9px', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                  >
                    {vulnClass}
                  </Link>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{location}</span>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '8px' }}>{(f.confidence_score * 100).toFixed(0)}%</span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Replace HumanGate.tsx with terminal gate bar**

```tsx
import { useState } from 'react'
import { gatesApi } from '../api/gates'
import { useEngagementStore } from '../store/engagement'
import type { Engagement } from '../types'

interface HumanGateProps {
  engagement: Engagement
}

export function HumanGate({ engagement }: HumanGateProps) {
  const upsertEngagement = useEngagementStore((s) => s.upsertEngagement)
  const [loading, setLoading] = useState<'approve' | 'reject' | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (engagement.status !== 'paused_at_gate') return null

  async function decide(approved: boolean) {
    setLoading(approved ? 'approve' : 'reject')
    setError(null)
    try {
      const updated = await gatesApi.decide(engagement.id, approved)
      upsertEngagement(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Decision failed')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div style={{ border: '1px solid var(--gate)', borderLeft: '2px solid var(--gate)', background: '#f59e0b08', padding: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span style={{ color: 'var(--gate)', fontSize: '9px', letterSpacing: '1px' }}>⚠ HUMAN GATE — {engagement.gate_status}</span>
      </div>
      <div style={{ color: '#f59e0b80', fontSize: '9px', marginBottom: '10px' }}>
        approval required before proceeding to next phase
      </div>
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          onClick={() => decide(true)}
          disabled={loading !== null}
          style={{ flex: 1, padding: '5px 0', background: 'transparent', border: '1px solid var(--complete)', color: 'var(--complete)', fontSize: '9px', letterSpacing: '1px', opacity: loading ? 0.5 : 1 }}
        >
          {loading === 'approve' ? 'APPROVING...' : '[APPROVE]'}
        </button>
        <button
          onClick={() => decide(false)}
          disabled={loading !== null}
          style={{ flex: 1, padding: '5px 0', background: 'transparent', border: '1px solid var(--aborted)', color: 'var(--aborted)', fontSize: '9px', letterSpacing: '1px', opacity: loading ? 0.5 : 1 }}
        >
          {loading === 'reject' ? 'REJECTING...' : '[REJECT]'}
        </button>
      </div>
      {error && <div style={{ color: 'var(--crit)', fontSize: '8px', marginTop: '6px' }}>{error}</div>}
    </div>
  )
}
```

- [ ] **Step 3: Verify build**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1 | tail -5
```

Expected: clean build.

- [ ] **Step 4: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE && git add frontend/src/components/FindingsPanel.tsx frontend/src/components/HumanGate.tsx && git commit -m "style: FindingsPanel + HumanGate — terminal table + gate bar"
```

---

### Task 7: FindingDetail Page

**Files:**
- Modify: `frontend/src/pages/FindingDetail.tsx`

- [ ] **Step 1: Replace FindingDetail.tsx with terminal detail layout**

This is a full replacement keeping all existing logic intact, converting only the visual layer.

```tsx
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { findingsApi } from '../api/findings'
import { ExploitWalkthrough } from '../components/ExploitWalkthrough'
import { AttackPathDiagram } from '../components/AttackPathDiagram'
import { PoCScript } from '../components/PoCScript'
import { ExploitSequenceDiagram } from '../components/ExploitSequenceDiagram'
import type { FindingDetail, Severity } from '../types'

const SEV_COLOR: Record<Severity, string> = {
  critical: 'var(--crit)',
  high:     'var(--high)',
  medium:   'var(--medium)',
  low:      'var(--low)',
  info:     'var(--info)',
}

const VERDICT_COLOR: Record<string, string> = {
  confirmed:   'var(--complete)',
  failed:      'var(--crit)',
  inconclusive:'var(--gate)',
}

const DIFFICULTY_COLOR: Record<string, string> = {
  easy:   'var(--crit)',
  medium: 'var(--medium)',
  hard:   'var(--complete)',
}

/* Reusable mini components */
function SectionHeader({ label }: { label: string }) {
  return (
    <div style={{ color: 'var(--accent)', fontSize: '8px', letterSpacing: '2px', borderBottom: '1px solid var(--border)', paddingBottom: '6px', marginBottom: '10px' }}>
      {label}
    </div>
  )
}

function Panel({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <div style={{ border: '1px solid var(--border)', borderLeft: `2px solid ${accent ?? 'var(--border)'}`, background: 'var(--surface)', padding: '12px', marginBottom: '12px' }}>
      {children}
    </div>
  )
}

function ActionButton({ onClick, disabled, children, danger }: { onClick: () => void; disabled: boolean; children: React.ReactNode; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{ padding: '5px 14px', background: 'transparent', border: `1px solid ${danger ? 'var(--crit)' : 'var(--accent-dim)'}`, color: danger ? 'var(--crit)' : 'var(--accent)', fontSize: '9px', letterSpacing: '1px', opacity: disabled ? 0.5 : 1 }}
    >
      {children}
    </button>
  )
}

export function FindingDetailPage() {
  const { engagementId, findingId } = useParams<{ engagementId: string; findingId: string }>()
  const navigate = useNavigate()
  const [finding, setFinding] = useState<FindingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [exploitLoading, setExploitLoading] = useState(false)
  const [pocLoading, setPocLoading] = useState(false)
  const [scriptLoading, setScriptLoading] = useState(false)
  const [executeLoading, setExecuteLoading] = useState(false)
  const [showExecuteModal, setShowExecuteModal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!findingId) return
    findingsApi
      .get(findingId)
      .then(setFinding)
      .catch(() => setError('Finding not found'))
      .finally(() => setLoading(false))
  }, [findingId])

  async function handleGeneratePoC() {
    if (!findingId) return
    setPocLoading(true)
    setError(null)
    try {
      const poc = await findingsApi.generatePoC(findingId)
      setFinding((prev) => (prev ? { ...prev, poc_detail: poc } : prev))
    } catch {
      setError('Failed to generate PoC.')
    } finally {
      setPocLoading(false)
    }
  }

  async function handleGenerateExploit() {
    if (!findingId) return
    setExploitLoading(true)
    setError(null)
    try {
      const exploit = await findingsApi.generateExploit(findingId)
      setFinding((prev) => (prev ? { ...prev, exploit_detail: exploit } : prev))
    } catch {
      setError('Failed to generate exploit.')
    } finally {
      setExploitLoading(false)
    }
  }

  async function handleGenerateExploitScript() {
    if (!findingId) return
    setScriptLoading(true)
    setError(null)
    try {
      const script = await findingsApi.generateExploitScript(findingId)
      setFinding((prev) => (prev ? { ...prev, exploit_script: script } : prev))
    } catch {
      setError('Failed to generate exploit script.')
    } finally {
      setScriptLoading(false)
    }
  }

  async function handleExecuteExploit() {
    if (!findingId) return
    setShowExecuteModal(false)
    setExecuteLoading(true)
    setError(null)
    try {
      const execution = await findingsApi.executeExploit(findingId)
      setFinding((prev) => (prev ? { ...prev, exploit_execution: execution } : prev))
    } catch {
      setError('Execution failed.')
    } finally {
      setExecuteLoading(false)
    }
  }

  async function handleOverrideVerdict(verdict: string) {
    if (!findingId) return
    try {
      const updated = await findingsApi.overrideVerdict(findingId, verdict)
      setFinding((prev) => (prev ? { ...prev, exploit_execution: updated } : prev))
    } catch {
      setError('Failed to override verdict.')
    }
  }

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', letterSpacing: '1px' }}>
        &gt; loading finding_
      </div>
    )
  }

  if (error || !finding) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px' }}>
        {error || 'finding not found'}
      </div>
    )
  }

  const vulnClass = finding.vulnerability_class ?? finding.attack_class ?? finding.title
  const location = finding.affected_surface ?? finding.endpoint ?? ''
  const evidence = Array.isArray(finding.evidence) ? finding.evidence.join('\n') : (finding.evidence ?? '')
  const activeVerdict = finding.exploit_execution?.override_verdict ?? finding.exploit_execution?.verdict
  const sevColor = SEV_COLOR[finding.severity]

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      {/* Execute confirmation modal */}
      {showExecuteModal && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.8)' }}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--crit)', padding: '20px', maxWidth: '400px', width: '100%', margin: '0 16px' }}>
            <div style={{ color: 'var(--crit)', fontSize: '10px', letterSpacing: '1px', marginBottom: '10px' }}>⚠ LIVE EXPLOIT EXECUTION</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '9px', marginBottom: '8px' }}>This will run a fully weaponized exploit against:</div>
            <div style={{ color: 'var(--high)', fontSize: '9px', background: 'var(--bg)', padding: '6px 10px', marginBottom: '8px', border: '1px solid var(--border)' }}>{location}</div>
            {finding.exploit_script && (
              <div style={{ color: 'var(--text-dim)', fontSize: '8px', marginBottom: '8px' }}>Impact: {finding.exploit_script.impact_achieved}</div>
            )}
            <div style={{ color: 'var(--gate)', fontSize: '8px', marginBottom: '12px' }}>Only proceed on systems you own or have explicit written permission to test.</div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={handleExecuteExploit}
                style={{ flex: 1, padding: '6px 0', background: 'transparent', border: '1px solid var(--crit)', color: 'var(--crit)', fontSize: '9px', letterSpacing: '1px', cursor: 'pointer' }}
              >
                EXECUTE
              </button>
              <button
                onClick={() => setShowExecuteModal(false)}
                style={{ flex: 1, padding: '6px 0', background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: '9px', letterSpacing: '1px', cursor: 'pointer' }}
              >
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={() => navigate(`/engagement/${engagementId}`)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: '9px', letterSpacing: '1px', padding: 0, cursor: 'pointer' }}
        >
          ← BACK
        </button>
        <span style={{ color: 'var(--text-label)', fontSize: '9px' }}>/</span>
        <span style={{ color: sevColor, fontSize: '9px', letterSpacing: '1px', border: `1px solid ${sevColor}40`, padding: '2px 8px' }}>[{finding.severity.toUpperCase()}]</span>
        <span style={{ color: 'var(--text-primary)', fontSize: '11px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{vulnClass}</span>
        <span style={{ color: 'var(--text-secondary)', fontSize: '9px' }}>CONF: {(finding.confidence_score * 100).toFixed(0)}%</span>
      </div>

      <div style={{ padding: '16px 24px', maxWidth: '1200px' }}>
        {/* Metadata grid */}
        <Panel accent={sevColor}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>SURFACE</div>
              <div style={{ color: 'var(--text-primary)', fontSize: '10px', fontFamily: 'inherit' }}>{location || '—'}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>CLASS</div>
              <div style={{ color: 'var(--text-primary)', fontSize: '10px' }}>{vulnClass}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>VERDICT</div>
              <div style={{ color: activeVerdict ? VERDICT_COLOR[activeVerdict] : 'var(--text-secondary)', fontSize: '10px', letterSpacing: '1px' }}>
                {activeVerdict?.toUpperCase() ?? 'PENDING'}
              </div>
            </div>
          </div>
        </Panel>

        {/* Description + Evidence */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
          <Panel>
            <SectionHeader label="DESCRIPTION" />
            <p style={{ color: 'var(--text-secondary)', fontSize: '9px', lineHeight: 1.6, margin: 0 }}>
              {finding.description || 'No description provided.'}
            </p>
          </Panel>
          <Panel>
            <SectionHeader label="EVIDENCE" />
            <pre style={{ color: 'var(--text-secondary)', fontSize: '8px', background: 'var(--bg)', padding: '8px', border: '1px solid var(--border)', overflowX: 'auto', maxHeight: '160px', margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {evidence || 'No evidence captured.'}
            </pre>
          </Panel>
        </div>

        {/* Exploit Intelligence */}
        <Panel>
          <SectionHeader label="EXPLOIT INTELLIGENCE" />
          {finding.exploit_detail ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '6px' }}>WALKTHROUGH</div>
                <ExploitWalkthrough steps={finding.exploit_detail.walkthrough} />
              </div>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '6px' }}>ATTACK PATH</div>
                <AttackPathDiagram source={finding.exploit_detail.attack_path_mermaid} />
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', marginTop: '8px' }}>
                  <div style={{ border: '1px solid var(--border)', padding: '6px' }}>
                    <div style={{ color: 'var(--text-label)', fontSize: '7px', letterSpacing: '1px', marginBottom: '3px' }}>DIFFICULTY</div>
                    <div style={{ color: DIFFICULTY_COLOR[finding.exploit_detail.difficulty] ?? 'var(--text-primary)', fontSize: '9px', letterSpacing: '1px' }}>
                      {finding.exploit_detail.difficulty.toUpperCase()}
                    </div>
                  </div>
                  <div style={{ border: '1px solid var(--border)', padding: '6px', gridColumn: 'span 2' }}>
                    <div style={{ color: 'var(--text-label)', fontSize: '7px', letterSpacing: '1px', marginBottom: '3px' }}>IMPACT</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '8px' }}>{finding.exploit_detail.impact}</div>
                  </div>
                </div>
                {finding.exploit_detail.prerequisites.length > 0 && (
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ color: 'var(--text-label)', fontSize: '7px', letterSpacing: '1px', marginBottom: '4px' }}>PREREQUISITES</div>
                    <ul style={{ margin: 0, paddingLeft: '14px', color: 'var(--text-secondary)', fontSize: '8px' }}>
                      {finding.exploit_detail.prerequisites.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px', padding: '12px 0' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: '9px' }}>&gt; no exploit intelligence generated yet_</div>
              <ActionButton onClick={handleGenerateExploit} disabled={exploitLoading}>
                {exploitLoading ? 'GENERATING...' : '▶ GENERATE EXPLOIT'}
              </ActionButton>
              {error && <div style={{ color: 'var(--crit)', fontSize: '8px' }}>{error}</div>}
            </div>
          )}
        </Panel>

        {/* PoC Script */}
        <Panel>
          <SectionHeader label="POC SCRIPT" />
          {finding.poc_detail ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '6px' }}>SCRIPT</div>
                <PoCScript poc={finding.poc_detail} />
              </div>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '6px' }}>EXPLOIT SEQUENCE</div>
                <ExploitSequenceDiagram source={finding.poc_detail.sequence_diagram} />
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px', padding: '12px 0' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: '9px' }}>&gt; no PoC script generated yet_</div>
              <ActionButton onClick={handleGeneratePoC} disabled={pocLoading}>
                {pocLoading ? 'GENERATING...' : '▶ GENERATE POC'}
              </ActionButton>
              {error && <div style={{ color: 'var(--crit)', fontSize: '8px' }}>{error}</div>}
            </div>
          )}
        </Panel>

        {/* Live Exploitation */}
        <Panel accent="var(--crit)">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
            <span style={{ color: 'var(--crit)', fontSize: '8px', letterSpacing: '2px' }}>LIVE EXPLOITATION</span>
            <span style={{ color: 'var(--crit)', fontSize: '7px', border: '1px solid var(--crit)40', padding: '1px 6px' }}>AUTHORIZED USE ONLY</span>
          </div>

          {/* Step 1: Weaponized Script */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '8px' }}>STEP 1 — WEAPONIZED SCRIPT</div>
            {finding.exploit_script ? (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '8px', border: '1px solid var(--border)', padding: '1px 6px' }}>{finding.exploit_script.language}</span>
                  <span style={{ color: 'var(--text-primary)', fontSize: '9px' }}>{finding.exploit_script.filename}</span>
                  <button
                    onClick={() => {
                      const blob = new Blob([finding.exploit_script!.script], { type: 'text/plain' })
                      const url = URL.createObjectURL(blob)
                      const a = document.createElement('a')
                      a.href = url
                      a.download = finding.exploit_script!.filename
                      a.click()
                      URL.revokeObjectURL(url)
                    }}
                    style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: '8px', padding: '2px 8px', cursor: 'pointer' }}
                  >
                    ↓ DOWNLOAD
                  </button>
                </div>
                <pre style={{ color: 'var(--accent)', fontSize: '8px', background: 'var(--bg)', padding: '10px', border: '1px solid var(--accent-dim)', overflowX: 'auto', maxHeight: '200px', margin: '0 0 6px', fontFamily: 'inherit' }}>
                  {finding.exploit_script.script}
                </pre>
                <div style={{ color: 'var(--text-dim)', fontSize: '8px' }}>
                  Expected: <span style={{ color: 'var(--text-secondary)' }}>{finding.exploit_script.expected_output}</span>
                  {' '} // Impact: <span style={{ color: 'var(--crit)' }}>{finding.exploit_script.impact_achieved}</span>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                <ActionButton onClick={handleGenerateExploitScript} disabled={scriptLoading}>
                  {scriptLoading ? 'GENERATING...' : '▶ GENERATE EXPLOIT SCRIPT'}
                </ActionButton>
              </div>
            )}
          </div>

          {/* Step 2: Execute */}
          {finding.exploit_script && (
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '8px' }}>STEP 2 — EXECUTE AGAINST TARGET</div>
              {finding.exploit_execution ? (
                <div>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', border: `1px solid ${VERDICT_COLOR[activeVerdict ?? 'inconclusive']}40`, padding: '4px 10px', marginBottom: '8px' }}>
                    <span style={{ color: VERDICT_COLOR[activeVerdict ?? 'inconclusive'], fontSize: '9px', letterSpacing: '1px' }}>
                      {(activeVerdict ?? 'INCONCLUSIVE').toUpperCase()} ({Math.round(finding.exploit_execution.confidence * 100)}%)
                    </span>
                    {finding.exploit_execution.override_verdict && (
                      <span style={{ color: 'var(--text-dim)', fontSize: '7px' }}>// overridden</span>
                    )}
                  </div>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '9px', marginBottom: '8px' }}>{finding.exploit_execution.reasoning}</p>
                  {finding.exploit_execution.stdout && (
                    <pre style={{ color: 'var(--complete)', fontSize: '8px', background: 'var(--bg)', padding: '8px', border: '1px solid var(--border)', overflowX: 'auto', maxHeight: '160px', margin: '0 0 8px', fontFamily: 'inherit' }}>
                      {finding.exploit_execution.stdout}
                    </pre>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: 'var(--text-dim)', fontSize: '8px' }}>override:</span>
                    {(['confirmed', 'failed', 'inconclusive'] as const).map((v) => (
                      <button
                        key={v}
                        onClick={() => handleOverrideVerdict(v)}
                        style={{ padding: '2px 8px', background: activeVerdict === v ? 'var(--border)' : 'transparent', border: `1px solid ${activeVerdict === v ? 'var(--accent)' : 'var(--border)'}`, color: activeVerdict === v ? 'var(--accent)' : 'var(--text-secondary)', fontSize: '8px', letterSpacing: '1px', cursor: 'pointer' }}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                  {finding.exploit_execution.timed_out && (
                    <div style={{ color: 'var(--gate)', fontSize: '8px', marginTop: '6px' }}>⚠ execution timed out</div>
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                  <ActionButton onClick={() => setShowExecuteModal(true)} disabled={executeLoading} danger>
                    {executeLoading ? 'EXECUTING...' : '⚠ EXECUTE AGAINST TARGET'}
                  </ActionButton>
                  {error && <div style={{ color: 'var(--crit)', fontSize: '8px' }}>{error}</div>}
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1 | tail -10
```

Expected: clean TypeScript + Vite build, no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/hemparekh/Desktop/FORGE && git add frontend/src/pages/FindingDetail.tsx && git commit -m "style: FindingDetail — terminal layout with metadata grid + code panels"
```

---

### Task 8: Final Verification

**Files:** None modified — verification only.

- [ ] **Step 1: Full TypeScript + build check**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run build 2>&1
```

Expected: `✓ built in` message with no TypeScript errors.

- [ ] **Step 2: Start dev server and visually verify all pages**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npm run dev &
```

Open `http://localhost:5173` and verify:
- Home: pure black bg, cyan FORGE header, process table visible
- Click any engagement → Engagement page: terminal header, two-column swarm/findings layout
- Click a finding → Finding Detail: metadata grid, cyan code block, terminal panels

- [ ] **Step 3: Final commit + push**

```bash
cd /Users/hemparekh/Desktop/FORGE && git push
```
