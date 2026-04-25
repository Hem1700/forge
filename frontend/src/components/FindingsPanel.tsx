import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import type { Severity, TriageStatus } from '../types'

const SEV_COLOR: Record<Severity, string> = {
  critical: 'var(--crit)',
  high:     'var(--high)',
  medium:   'var(--medium)',
  low:      'var(--low)',
  info:     'var(--info)',
}

const TRIAGE_LABEL: Record<TriageStatus, string> = {
  unreviewed:     'NEW',
  accepted:       'ACCEPT',
  false_positive: 'FP',
  fixed:          'FIXED',
}

const TRIAGE_COLOR: Record<TriageStatus, string> = {
  unreviewed:     'var(--accent-glow)',
  accepted:       'var(--running)',
  false_positive: 'var(--text-secondary)',
  fixed:          'var(--complete)',
}

const COLS = '70px 2fr 1fr 60px 70px 60px'

const ALL_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'info']
const ALL_TRIAGE: (TriageStatus | 'all')[] = ['all', 'unreviewed', 'accepted', 'false_positive', 'fixed']

export function FindingsPanel() {
  const findings = useEngagementStore((s) => s.findings)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)

  const [sevFilter, setSevFilter] = useState<Set<Severity>>(new Set(ALL_SEVERITIES))
  const [triageFilter, setTriageFilter] = useState<TriageStatus | 'all'>('all')
  const [search, setSearch] = useState('')

  const baseFiltered = useMemo(
    () => (activeEngagement ? findings.filter((f) => f.engagement_id === activeEngagement.id) : findings),
    [findings, activeEngagement],
  )

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    return baseFiltered.filter((f) => {
      if (!sevFilter.has(f.severity)) return false
      const triage = (f.triage_status ?? 'unreviewed') as TriageStatus
      if (triageFilter !== 'all' && triage !== triageFilter) return false
      if (!q) return true
      const haystack = [
        f.title, f.vulnerability_class, f.attack_class, f.affected_surface,
        f.endpoint, f.description, Array.isArray(f.evidence) ? f.evidence.join(' ') : f.evidence,
      ].filter(Boolean).join(' ').toLowerCase()
      return haystack.includes(q)
    })
  }, [baseFiltered, sevFilter, triageFilter, search])

  function toggleSev(s: Severity) {
    setSevFilter((cur) => {
      const next = new Set(cur)
      if (next.has(s)) next.delete(s); else next.add(s)
      // Don't allow zero — empty set means "show none" which is hostile
      return next.size === 0 ? new Set([s]) : next
    })
  }

  return (
    <div style={{ border: '1px solid var(--border)', background: 'var(--surface)', padding: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '8px', marginBottom: '8px', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ color: 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '2px' }}>FINDINGS</span>
          <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-sm)', border: '1px solid var(--border)', padding: '1px 6px' }}>
            {visible.length}{visible.length !== baseFiltered.length && ` / ${baseFiltered.length}`}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          {ALL_SEVERITIES.map((s) => {
            const on = sevFilter.has(s)
            return (
              <button
                key={s}
                onClick={() => toggleSev(s)}
                style={{
                  background: on ? 'transparent' : 'var(--bg)',
                  border: `1px solid ${on ? SEV_COLOR[s] : 'var(--border)'}`,
                  color: on ? SEV_COLOR[s] : 'var(--text-dim)',
                  fontSize: 'var(--fs-tiny)', letterSpacing: '1px', padding: '2px 6px', cursor: 'pointer',
                }}
              >
                {s.toUpperCase().slice(0, 4)}
              </button>
            )
          })}
          <select
            value={triageFilter}
            onChange={(e) => setTriageFilter(e.target.value as TriageStatus | 'all')}
            style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: 'var(--fs-tiny)', letterSpacing: '1px', padding: '2px 4px', cursor: 'pointer' }}
          >
            {ALL_TRIAGE.map((t) => <option key={t} value={t}>{t === 'all' ? 'ALL TRIAGE' : t.toUpperCase().replace('_', ' ')}</option>)}
          </select>
          <input
            type="text"
            placeholder="search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-tiny)', padding: '2px 6px', outline: 'none', width: '160px' }}
          />
        </div>
      </div>

      {visible.length === 0 ? (
        <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', padding: '12px 0' }}>
          {baseFiltered.length === 0 ? <>&gt; no findings yet_</> : <>&gt; no findings match the current filter_</>}
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', borderBottom: '1px solid var(--border)', paddingBottom: '4px', marginBottom: '2px' }}>
            <span>SEV</span>
            <span>VULNERABILITY</span>
            <span>LOCATION</span>
            <span>CONF</span>
            <span>TRIAGE</span>
            <span></span>
          </div>
          <div style={{ maxHeight: '420px', overflowY: 'auto' }}>
            {visible.map((f) => {
              const vulnClass = f.vulnerability_class ?? f.attack_class ?? f.title
              const location = f.affected_surface ?? f.endpoint ?? ''
              const triage = (f.triage_status ?? 'unreviewed') as TriageStatus
              return (
                <div key={f.id} style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid var(--border-deep)' }}>
                  <span style={{ color: SEV_COLOR[f.severity], fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>[{f.severity.toUpperCase().slice(0, 4)}]</span>
                  <Link
                    to={`/engagement/${f.engagement_id}/findings/${f.id}`}
                    style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-sm)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                  >
                    {vulnClass}
                  </Link>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{location}</span>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>{(f.confidence_score * 100).toFixed(0)}%</span>
                  <span style={{ color: TRIAGE_COLOR[triage], fontSize: 'var(--fs-tiny)', letterSpacing: '1px' }}>{TRIAGE_LABEL[triage]}</span>
                  <Link
                    to={`/engagement/${f.engagement_id}/findings/${f.id}`}
                    style={{ color: 'var(--accent-glow)', fontSize: 'var(--fs-xs)', textDecoration: 'none' }}
                  >
                    [view]
                  </Link>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
