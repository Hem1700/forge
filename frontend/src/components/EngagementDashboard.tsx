import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import type { Engagement, EngagementStatus } from '../types'

const STATUS_COLORS: Record<EngagementStatus, string> = {
  pending: 'bg-gray-700 text-gray-200',
  running: 'bg-green-700 text-green-100',
  paused_at_gate: 'bg-yellow-700 text-yellow-100',
  complete: 'bg-blue-700 text-blue-100',
  aborted: 'bg-red-700 text-red-100',
}

export function EngagementDashboard() {
  const engagements = useEngagementStore((s) => s.engagements)
  const setEngagements = useEngagementStore((s) => s.setEngagements)
  const navigate = useNavigate()

  const [showForm, setShowForm] = useState(false)
  const [targetUrl, setTargetUrl] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!targetUrl.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await engagementsApi.create({ target_url: targetUrl.trim() })
      const list = await engagementsApi.list()
      setEngagements(list)
      setTargetUrl('')
      setShowForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create engagement')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-gray-100">Engagements</h2>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-md font-medium transition-colors"
        >
          {showForm ? 'Cancel' : '+ New Engagement'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="mb-6 p-4 bg-gray-900 border border-gray-800 rounded-lg">
          <label className="block text-sm text-gray-300 mb-2">Target URL</label>
          <div className="flex gap-2">
            <input
              type="url"
              required
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="https://target.example.com"
              className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 focus:outline-none focus:border-orange-500"
            />
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-600 text-white rounded-md font-medium"
            >
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
          {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
        </form>
      )}

      {engagements.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No engagements yet. Create one to begin.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {engagements.map((eng) => (
            <EngagementCard key={eng.id} engagement={eng} onClick={() => navigate(`/engagement/${eng.id}`)} />
          ))}
        </div>
      )}
    </div>
  )
}

interface EngagementCardProps {
  engagement: Engagement
  onClick: () => void
}

function EngagementCard({ engagement, onClick }: EngagementCardProps) {
  return (
    <button
      onClick={onClick}
      className="text-left p-4 bg-gray-900 border border-gray-800 rounded-lg hover:border-orange-500 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className="font-medium text-gray-100 truncate flex-1 mr-2">{engagement.target_url}</h3>
        <span className={`text-xs px-2 py-1 rounded-full whitespace-nowrap ${STATUS_COLORS[engagement.status]}`}>
          {engagement.status}
        </span>
      </div>
      <div className="text-xs text-gray-500 mb-1">Gate: {engagement.gate_status}</div>
      <div className="text-xs text-gray-500">{new Date(engagement.created_at).toLocaleString()}</div>
    </button>
  )
}
