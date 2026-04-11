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
    <div className="bg-yellow-950/40 border border-yellow-700 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
        <h3 className="font-semibold text-yellow-100">Human Gate: {engagement.gate_status}</h3>
      </div>
      <p className="text-sm text-yellow-200/80 mb-4">
        Approval required before proceeding to next phase.
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => decide(true)}
          disabled={loading !== null}
          className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white rounded-md font-medium transition-colors"
        >
          {loading === 'approve' ? 'Approving...' : 'Approve'}
        </button>
        <button
          onClick={() => decide(false)}
          disabled={loading !== null}
          className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white rounded-md font-medium transition-colors"
        >
          {loading === 'reject' ? 'Rejecting...' : 'Reject (Abort)'}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </div>
  )
}
