# OS Scan Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OS target form, progress display for OS pipeline events, and chain finding visual treatment to the existing FORGE frontend.

**Architecture:** Three surgical edits to existing files — types, API client, and three components. The EngagementDashboard gains OS form state; SwarmMonitor gains OS event rendering; FindingsPanel gains a chain badge. No new files needed.

**Tech Stack:** React 18, TypeScript, Zustand, Vite, inline CSS with CSS variables (matches codebase)

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/types/index.ts` | Add `'os'` to `TargetType`; add `finding_type`, `chain_steps`, `component_finding_ids` to `Finding`; add OS event types to `SwarmEvent` |
| `frontend/src/api/engagements.ts` | Add `createOsTarget()` method |
| `frontend/src/components/EngagementDashboard.tsx` | Add OS form state + fields + create-and-start flow |
| `frontend/src/components/SwarmMonitor.tsx` | Add OS event type cases to `renderEvent()` |
| `frontend/src/components/FindingsPanel.tsx` | Chain badge + expanded row for chain findings |

---

### Task 1: Update types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add `'os'` to TargetType and OS fields to Finding**

In `frontend/src/types/index.ts`, make the following changes:

Change line 4:
```typescript
export type TargetType = 'web' | 'local_codebase' | 'binary' | 'cve'
```
to:
```typescript
export type TargetType = 'web' | 'local_codebase' | 'binary' | 'cve' | 'os'
```

Add `finding_type`, `chain_steps`, `component_finding_ids` to the `Finding` interface (after `created_at`):
```typescript
  finding_type?: 'chain' | null
  chain_steps?: string[] | null
  component_finding_ids?: string[] | null
```

Extend `SwarmEvent.type` to include OS event types. Change:
```typescript
  type: 'agent_started' | 'agent_completed' | 'finding_discovered' | 'finding_judged' | 'agent_thought' | 'gate_triggered' | 'campaign_complete' | 'progress' | 'ping' | 'stream_error'
```
to:
```typescript
  type: 'agent_started' | 'agent_completed' | 'finding_discovered' | 'finding_judged' | 'agent_thought' | 'gate_triggered' | 'campaign_complete' | 'progress' | 'ping' | 'stream_error' | 'os_modeling_started' | 'os_modeling_complete' | 'os_modeling_failed' | 'os_agents_started' | 'os_agent_started' | 'os_agent_complete' | 'os_agent_failed' | 'os_pipeline_complete'
```

- [ ] **Step 2: Verify TypeScript compiles (no type errors so far)**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add os TargetType, chain Finding fields, OS SwarmEvent types"
```

---

### Task 2: Add `createOsTarget` API method

**Files:**
- Modify: `frontend/src/api/engagements.ts`

- [ ] **Step 1: Add the method**

After the existing `events` and before `downloadPdfReport`, add:
```typescript
  createOsTarget: (id: string, data: {
    host: string
    port: number
    username: string
    auth_type: 'key' | 'password' | 'agent'
    key_material?: string
  }) =>
    apiFetch<{ id: string; host: string; port: number }>(`/api/v1/engagements/${id}/os-target`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/engagements.ts
git commit -m "feat(api): add createOsTarget endpoint method"
```

---

### Task 3: OS target form in EngagementDashboard

**Files:**
- Modify: `frontend/src/components/EngagementDashboard.tsx`

- [ ] **Step 1: Add OS to the TYPE map and COLS**

Change the TYPE record (line 16–21) to:
```typescript
const TYPE: Record<TargetType, string> = {
  web: 'web',
  local_codebase: 'code',
  binary: 'binary',
  cve: 'cve',
  os: 'os',
}
```

- [ ] **Step 2: Add OS form state variables**

After the existing state declarations (around line 36–39), add:
```typescript
  const [osHost, setOsHost] = useState('')
  const [osPort, setOsPort] = useState(22)
  const [osUsername, setOsUsername] = useState('')
  const [osAuthType, setOsAuthType] = useState<'key' | 'password'>('key')
  const [osKeyMaterial, setOsKeyMaterial] = useState('')
```

- [ ] **Step 3: Add OS to the target type button list**

Change line 123:
```typescript
{(['web', 'local_codebase', 'binary', 'cve'] as TargetType[]).map((t) => (
```
to:
```typescript
{(['web', 'local_codebase', 'binary', 'cve', 'os'] as TargetType[]).map((t) => (
```

- [ ] **Step 4: Update `handleCreate` to handle OS type**

The OS flow creates an engagement then immediately calls `os-target` (which auto-starts the pipeline), then navigates. Replace the existing `handleCreate` function body with:

```typescript
  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      let payload: Parameters<typeof engagementsApi.create>[0]
      if (targetType === 'cve') {
        payload = { target_url: cveId.trim().toUpperCase(), target_type: 'cve' }
      } else if (targetType === 'web') {
        payload = { target_url: targetUrl.trim(), target_type: 'web' }
      } else if (targetType === 'os') {
        payload = { target_url: osHost.trim(), target_type: 'os' }
      } else {
        payload = { target_url: targetPath.trim() || 'local', target_type: targetType, target_path: targetPath.trim() }
      }
      const eng = await engagementsApi.create(payload)
      if (targetType === 'os') {
        await engagementsApi.createOsTarget(eng.id as unknown as string, {
          host: osHost.trim(),
          port: osPort,
          username: osUsername.trim(),
          auth_type: osAuthType,
          key_material: osKeyMaterial.trim() || undefined,
        })
        setOsHost('')
        setOsPort(22)
        setOsUsername('')
        setOsAuthType('key')
        setOsKeyMaterial('')
        setShowForm(false)
        navigate(`/engagement/${eng.id}`)
        return
      }
      const list = await engagementsApi.list()
      setEngagements(list)
      setTargetUrl('')
      setTargetPath('')
      setCveId('')
      setShowForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create engagement')
    } finally {
      setSubmitting(false)
    }
  }
```

- [ ] **Step 5: Add OS form fields in the form JSX**

After the CVE block (the last `} : (` branch before the closing `)}`) and before `{error && ...}`, add an `os` branch. The full conditional should end like:

```tsx
          ) : targetType === 'os' ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: '8px', marginBottom: '8px' }}>
                <div>
                  <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>HOST</div>
                  <input
                    type="text"
                    required
                    value={osHost}
                    onChange={(e) => setOsHost(e.target.value)}
                    placeholder="192.168.1.1 or hostname"
                    style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', outline: 'none', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>PORT</div>
                  <input
                    type="number"
                    required
                    min={1}
                    max={65535}
                    value={osPort}
                    onChange={(e) => setOsPort(Number(e.target.value))}
                    style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', outline: 'none', boxSizing: 'border-box' }}
                  />
                </div>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>USERNAME</div>
                <input
                  type="text"
                  required
                  value={osUsername}
                  onChange={(e) => setOsUsername(e.target.value)}
                  placeholder="root"
                  style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>AUTH_TYPE</div>
                <div style={{ display: 'flex', gap: '4px' }}>
                  {(['key', 'password'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setOsAuthType(t)}
                      style={{
                        flex: 1, padding: '4px 0', fontSize: 'var(--fs-xs)', letterSpacing: '1px',
                        background: osAuthType === t ? 'var(--accent-bg)' : 'transparent',
                        border: `1px solid ${osAuthType === t ? 'var(--accent)' : 'var(--border)'}`,
                        color: osAuthType === t ? 'var(--accent)' : 'var(--text-secondary)',
                      }}
                    >
                      {t === 'key' ? 'SSH KEY' : 'PASSWORD'}
                    </button>
                  ))}
                </div>
              </div>
              {osAuthType === 'key' ? (
                <div style={{ marginBottom: '8px' }}>
                  <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>SSH_PRIVATE_KEY</div>
                  <textarea
                    value={osKeyMaterial}
                    onChange={(e) => setOsKeyMaterial(e.target.value)}
                    placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."
                    rows={5}
                    style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-sm)', outline: 'none', boxSizing: 'border-box', resize: 'vertical', fontFamily: 'monospace' }}
                  />
                </div>
              ) : (
                <div style={{ marginBottom: '8px' }}>
                  <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>PASSWORD</div>
                  <input
                    type="password"
                    value={osKeyMaterial}
                    onChange={(e) => setOsKeyMaterial(e.target.value)}
                    placeholder="SSH password"
                    style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', outline: 'none', boxSizing: 'border-box' }}
                  />
                </div>
              )}
            </div>
          ) : (
```

- [ ] **Step 6: Change submit button label for OS**

The submit button currently always says `▶ CREATE ENGAGEMENT`. Change it to show a different label for OS:
```tsx
            {submitting ? 'CREATING...' : targetType === 'os' ? '▶ START OS SCAN' : '▶ CREATE ENGAGEMENT'}
```

- [ ] **Step 7: Verify TypeScript compiles**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npx tsc --noEmit 2>&1 | head -40
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/EngagementDashboard.tsx
git commit -m "feat(ui): add OS target form to NewEngagement flow"
```

---

### Task 4: OS event rendering in SwarmMonitor

**Files:**
- Modify: `frontend/src/components/SwarmMonitor.tsx`

- [ ] **Step 1: Add OS event cases to `renderEvent()`**

Before the `case 'ping':` / `default:` case, add:

```typescript
    case 'os_modeling_started': {
      const host = (p.host ?? '') as string
      return {
        tag: 'OS', tagColor: 'var(--accent)',
        msg: <><span style={K}>fingerprinting</span> <span style={V}>{host}</span></>,
      }
    }
    case 'os_modeling_complete': {
      const host = (p.host ?? '') as string
      const pkgs = p.packages as number | undefined
      const ports = p.open_ports as number | undefined
      return {
        tag: 'OS', tagColor: 'var(--complete)',
        msg: (
          <>
            <span style={K}>{host}</span> fingerprinted
            {pkgs != null && <> · <span style={V}>{pkgs} pkg</span></>}
            {ports != null && <> · <span style={V}>{ports} port</span></>}
          </>
        ),
      }
    }
    case 'os_modeling_failed': {
      const err = (p.error ?? '') as string
      return {
        tag: 'OS', tagColor: 'var(--crit)',
        msg: <><span style={{ color: 'var(--crit)' }}>fingerprint failed</span>{err && <> · {err}</>}</>,
      }
    }
    case 'os_agents_started': {
      const agentsArr = (p.agents ?? []) as string[]
      return {
        tag: 'OS', tagColor: 'var(--accent)',
        msg: <><span style={K}>agents launched</span> <span style={V}>{agentsArr.join(', ')}</span></>,
      }
    }
    case 'os_agent_started': {
      const agentType = (p.agent_type ?? '') as string
      return {
        tag: 'OS', tagColor: 'var(--accent)',
        msg: <><span style={K}>{agentType}</span> <span style={V}>started</span></>,
      }
    }
    case 'os_agent_complete': {
      const agentType = (p.agent_type ?? '') as string
      const count = p.findings as number | undefined
      return {
        tag: 'OS', tagColor: 'var(--complete)',
        msg: (
          <>
            <span style={K}>{agentType}</span> done
            {count != null && <> · <span style={V}>{count} finding{count !== 1 ? 's' : ''}</span></>}
          </>
        ),
      }
    }
    case 'os_agent_failed': {
      const agentType = (p.agent_type ?? '') as string
      const err = (p.error ?? '') as string
      return {
        tag: 'OS', tagColor: 'var(--crit)',
        msg: <><span style={K}>{agentType}</span> <span style={{ color: 'var(--crit)' }}>failed</span>{err && <> · {err}</>}</>,
      }
    }
    case 'os_pipeline_complete': {
      const total = p.total_findings as number | undefined
      const host = (p.host ?? '') as string
      return {
        tag: 'OS', tagColor: 'var(--complete)',
        msg: (
          <>
            <span style={K}>pipeline complete</span>
            {host && <> · <span style={V}>{host}</span></>}
            {total != null && <> · <span style={V}>{total} total finding{total !== 1 ? 's' : ''}</span></>}
          </>
        ),
      }
    }
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SwarmMonitor.tsx
git commit -m "feat(ui): render OS pipeline events in SwarmMonitor"
```

---

### Task 5: Chain finding visual treatment in FindingsPanel

**Files:**
- Modify: `frontend/src/components/FindingsPanel.tsx`

- [ ] **Step 1: Add chain badge to finding rows**

In the finding row render, after the triage status span, add a chain indicator. The chain badge goes in the VULNERABILITY cell: prepend a chain icon when `f.finding_type === 'chain'`.

Change the `<Link>` cell for the vulnerability class:
```tsx
                  <Link
                    to={`/engagement/${f.engagement_id}/findings/${f.id}`}
                    style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-sm)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                  >
                    {vulnClass}
                  </Link>
```
to:
```tsx
                  <Link
                    to={`/engagement/${f.engagement_id}/findings/${f.id}`}
                    style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-sm)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '5px' }}
                  >
                    {f.finding_type === 'chain' && (
                      <span
                        title={`Attack chain: ${(f.chain_steps ?? []).length} steps`}
                        style={{ flexShrink: 0, fontSize: 'var(--fs-tiny)', letterSpacing: '1px', color: 'var(--crit)', border: '1px solid var(--crit)', padding: '0 4px', lineHeight: '14px' }}
                      >
                        CHAIN
                      </span>
                    )}
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{vulnClass}</span>
                  </Link>
```

- [ ] **Step 2: Add chain steps tooltip row under chain findings**

After the closing `</div>` of the row grid div but still inside `visible.map`, add an expandable chain steps section. Replace the outer `return (...)` for each finding:

The row currently is a `<div>` with `display: grid`. Wrap it in a fragment and add a conditional chain-steps row:

```tsx
                return (
                  <div key={f.id}>
                    <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', alignItems: 'center', padding: '5px 0', borderBottom: f.finding_type === 'chain' ? 'none' : '1px solid var(--border-deep)' }}>
                      {/* ... existing cells ... */}
                    </div>
                    {f.finding_type === 'chain' && f.chain_steps && f.chain_steps.length > 0 && (
                      <div style={{ padding: '4px 0 6px 8px', borderBottom: '1px solid var(--border-deep)', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        {f.chain_steps.map((step, i) => (
                          <div key={i} style={{ display: 'flex', gap: '6px', alignItems: 'baseline' }}>
                            <span style={{ color: 'var(--crit)', fontSize: 'var(--fs-tiny)', flexShrink: 0 }}>{i + 1}.</span>
                            <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>{step}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/FindingsPanel.tsx
git commit -m "feat(ui): chain finding badge and step list in FindingsPanel"
```

---

### Task 6: Final check and push

- [ ] **Step 1: Run full TypeScript check**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npx tsc --noEmit 2>&1
```
Expected: no output (zero errors)

- [ ] **Step 2: Run ESLint**

```bash
cd /Users/hemparekh/Desktop/FORGE/frontend && npx eslint src/ --ext .ts,.tsx 2>&1 | head -40
```

- [ ] **Step 3: Push to origin/main**

```bash
git push origin main
```
