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
