import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import { useSwarmStream } from '../hooks/useSwarmStream'
import { SwarmMonitor } from '../components/SwarmMonitor'
import { HumanGate } from '../components/HumanGate'
import { FindingsPanel } from '../components/FindingsPanel'
import { ReportViewer } from '../components/ReportViewer'
import type { EngagementStatus, Finding, Severity, TargetType } from '../types'

const STATUS: Record<EngagementStatus, { color: string; label: string }> = {
  running:        { color: 'var(--running)', label: '● RUNNING' },
  complete:       { color: 'var(--complete)', label: '✓ COMPLETE' },
  paused_at_gate: { color: 'var(--gate)',    label: '⊘ GATE' },
  pending:        { color: 'var(--pending)', label: '○ PENDING' },
  aborted:        { color: 'var(--aborted)', label: '✕ ABORTED' },
}

const STATUS_DIM: Record<EngagementStatus, string> = {
  running:        'var(--running-dim)',
  complete:       'var(--complete-dim)',
  paused_at_gate: 'var(--gate-dim)',
  pending:        'var(--pending-dim)',
  aborted:        'var(--aborted-dim)',
}

const TYPE_LABEL: Record<TargetType, string> = {
  web: 'web',
  local_codebase: 'code',
  binary: 'binary',
}

const SEV_COLOR: Record<Severity, string> = {
  critical: 'var(--crit)',
  high:     'var(--high)',
  medium:   'var(--medium)',
  low:      'var(--low)',
  info:     'var(--info)',
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: '10px 14px', borderRight: '1px solid var(--border)' }}>
      <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: 'var(--fs-md)', letterSpacing: '1px' }}>{children}</div>
    </div>
  )
}

function FindingsBreakdown({ findings }: { findings: Finding[] }) {
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  findings.forEach((f) => { counts[f.severity] = (counts[f.severity] ?? 0) + 1 })
  const chips: [Severity, string][] = [['critical', 'C'], ['high', 'H'], ['medium', 'M'], ['low', 'L']]
  return (
    <span style={{ color: 'var(--text-primary)' }}>
      {findings.length}
      {chips.filter(([s]) => counts[s] > 0).map(([s, letter]) => (
        <span key={s} style={{ color: SEV_COLOR[s], marginLeft: '8px', fontSize: 'var(--fs-sm)' }}>·{counts[s]}{letter}</span>
      ))}
    </span>
  )
}

export function Engagement() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const setActiveEngagement = useEngagementStore((s) => s.setActiveEngagement)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)
  const setFindings = useEngagementStore((s) => s.setFindings)
  const setEvents = useEngagementStore((s) => s.setEvents)
  const findings = useEngagementStore((s) => s.findings)
  const agents = useEngagementStore((s) => s.agents)
  const [pdfLoading, setPdfLoading] = useState(false)

  useEffect(() => {
    if (!id) return
    engagementsApi.get(id).then(setActiveEngagement).catch(console.error)
    engagementsApi.findings(id).then(setFindings).catch(console.error)
    engagementsApi.events(id).then(setEvents).catch(console.error)
    return () => {
      setActiveEngagement(null)
      setFindings([])
      setEvents([])
    }
  }, [id, setActiveEngagement, setFindings, setEvents])

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
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--fs-md)', letterSpacing: '1px' }}>
        &gt; loading engagement_
      </div>
    )
  }

  const st = STATUS[activeEngagement.status]
  const label = activeEngagement.target_path ?? activeEngagement.target_url
  const engFindings = findings.filter((f) => f.engagement_id === activeEngagement.id)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      {/* Header */}
      <div style={{ borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={() => navigate(-1)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', padding: 0 }}
        >
          ← FORGE
        </button>
        <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-sm)' }}>/</span>
        <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-base)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
        <span style={{ color: st.color, fontSize: 'var(--fs-sm)', letterSpacing: '1px', border: `1px solid ${STATUS_DIM[activeEngagement.status]}`, padding: '2px 8px' }}>{st.label}</span>
        <button
          onClick={handleDownloadPdf}
          disabled={pdfLoading}
          style={{ background: 'transparent', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: 'var(--fs-sm)', padding: '3px 10px', letterSpacing: '1px', opacity: pdfLoading ? 0.5 : 1 }}
        >
          {pdfLoading ? '...' : 'PDF ↓'}
        </button>
      </div>

      {/* Body — single-column, console-first */}
      <div style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '1400px', margin: '0 auto' }}>
        {/* Human gate banner when paused */}
        <HumanGate engagement={activeEngagement} />

        {/* Live swarm console — the hero */}
        <SwarmMonitor />

        {/* Compact status strip */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', border: '1px solid var(--border)', background: 'var(--surface)' }}>
          <Stat label="TARGET_TYPE">
            <span>{TYPE_LABEL[activeEngagement.target_type]}</span>
          </Stat>
          <Stat label="AGENTS">
            <span style={{ color: 'var(--accent)' }}>{agents.length}</span>
          </Stat>
          <Stat label="FINDINGS">
            <FindingsBreakdown findings={engFindings} />
          </Stat>
          <div style={{ padding: '10px 14px' }}>
            <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>GATE</div>
            <div style={{ fontSize: 'var(--fs-md)', letterSpacing: '1px', color: st.color }}>{st.label}</div>
          </div>
        </div>

        {/* Findings table — full width */}
        <FindingsPanel />

        {/* Report viewer */}
        <ReportViewer engagementId={activeEngagement.id} />
      </div>
    </div>
  )
}
