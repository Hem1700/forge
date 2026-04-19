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

const STATUS_DIM: Record<EngagementStatus, string> = {
  running:        'var(--running-dim)',
  complete:       'var(--complete-dim)',
  paused_at_gate: 'var(--gate-dim)',
  pending:        'var(--pending-dim)',
  aborted:        'var(--aborted-dim)',
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
        <span style={{ color: st.color, fontSize: '9px', letterSpacing: '1px', border: `1px solid ${STATUS_DIM[activeEngagement.status]}`, padding: '2px 8px' }}>{st.label}</span>
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
