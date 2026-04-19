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
        <span style={{ color: 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '2px' }}>SWARM MONITOR</span>
        {agents.length > 0 && (
          <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-sm)', border: '1px solid var(--border)', padding: '1px 6px' }}>
            {agents.length} AGENT{agents.length === 1 ? '' : 'S'}
          </span>
        )}
      </div>

      {/* Event log */}
      <div style={{ maxHeight: '440px', overflowY: 'auto' }}>
        {recent.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', padding: '16px 0' }}>
            &gt; waiting for events_
          </div>
        ) : (
          recent.map((event, idx) => {
            const ts = new Date(event.timestamp).toLocaleTimeString('en-US', { hour12: false })
            return (
              <div key={idx} style={{ borderBottom: '1px solid var(--border-deep)', padding: '4px 0', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-xs)', flexShrink: 0, marginTop: '1px' }}>[{ts}]</span>
                <span style={{ color: EVENT_COLOR[event.type], fontSize: 'var(--fs-xs)', letterSpacing: '1px', flexShrink: 0 }}>{event.type}</span>
                <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', wordBreak: 'break-all' }}>
                  {JSON.stringify(event.payload)}
                </span>
              </div>
            )
          })
        )}
      </div>

      {/* Cursor */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '6px', marginTop: '6px', color: 'var(--accent-glow)', fontSize: 'var(--fs-sm)' }}>
        _
      </div>
    </div>
  )
}
