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
        <span style={{ color: 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '2px' }}>FINDINGS</span>
        <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-sm)', border: '1px solid var(--border)', padding: '1px 6px' }}>{filtered.length}</span>
      </div>

      {filtered.length === 0 ? (
        <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', padding: '12px 0' }}>
          &gt; no findings yet_
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', borderBottom: '1px solid var(--border)', paddingBottom: '4px', marginBottom: '2px' }}>
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
                  <span style={{ color: SEV_COLOR[f.severity], fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>[{f.severity.toUpperCase().slice(0, 4)}]</span>
                  <Link
                    to={`/engagement/${f.engagement_id}/findings/${f.id}`}
                    style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-sm)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                  >
                    {vulnClass}
                  </Link>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{location}</span>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>{(f.confidence_score * 100).toFixed(0)}%</span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
