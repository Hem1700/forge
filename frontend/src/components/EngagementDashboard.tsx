import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import type { Engagement, EngagementStatus, TargetType } from '../types'

const STATUS_COLORS: Record<EngagementStatus, string> = {
  pending: 'bg-gray-700 text-gray-200',
  running: 'bg-green-700 text-green-100',
  paused_at_gate: 'bg-yellow-700 text-yellow-100',
  complete: 'bg-blue-700 text-blue-100',
  aborted: 'bg-red-700 text-red-100',
}

const TARGET_TYPE_LABELS: Record<TargetType, string> = {
  web: 'Web App',
  local_codebase: 'Local Codebase',
  binary: 'Binary',
}

const TARGET_TYPE_ICONS: Record<TargetType, string> = {
  web: '🌐',
  local_codebase: '📁',
  binary: '⚙️',
}

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
        <form onSubmit={handleCreate} className="mb-6 p-4 bg-gray-900 border border-gray-800 rounded-lg space-y-3">
          {/* Target type selector */}
          <div>
            <label className="block text-sm text-gray-300 mb-2">Target Type</label>
            <div className="flex gap-2">
              {(['web', 'local_codebase', 'binary'] as TargetType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTargetType(t)}
                  className={`flex-1 py-2 px-3 rounded-md text-sm font-medium border transition-colors ${
                    targetType === t
                      ? 'border-orange-500 bg-orange-500/20 text-orange-300'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                  }`}
                >
                  {TARGET_TYPE_ICONS[t]} {TARGET_TYPE_LABELS[t]}
                </button>
              ))}
            </div>
          </div>

          {/* URL input (web) */}
          {targetType === 'web' && (
            <div>
              <label className="block text-sm text-gray-300 mb-1">Target URL</label>
              <input
                type="url"
                required
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                placeholder="https://target.example.com"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 focus:outline-none focus:border-orange-500"
              />
            </div>
          )}

          {/* Path input (local_codebase / binary) */}
          {targetType !== 'web' && (
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                {targetType === 'binary' ? 'Binary File Path' : 'Codebase Directory Path'}
              </label>
              <input
                type="text"
                required
                value={targetPath}
                onChange={(e) => setTargetPath(e.target.value)}
                placeholder={targetType === 'binary' ? '/path/to/binary' : '/Users/you/Desktop/myproject'}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-md text-gray-100 focus:outline-none focus:border-orange-500 font-mono text-sm"
              />
              <p className="mt-1 text-xs text-gray-500">Absolute path on the FORGE server filesystem</p>
            </div>
          )}

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-600 text-white rounded-md font-medium transition-colors"
          >
            {submitting ? 'Creating...' : 'Create Engagement'}
          </button>
        </form>
      )}

      {engagements.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No engagements yet. Create one to begin.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {engagements.map((eng) => (
            <EngagementCard
              key={eng.id}
              engagement={eng}
              starting={starting === eng.id}
              onClick={() => navigate(`/engagement/${eng.id}`)}
              onStart={(e) => handleStart(e, eng)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface EngagementCardProps {
  engagement: Engagement
  starting: boolean
  onClick: () => void
  onStart: (e: React.MouseEvent) => void
}

function EngagementCard({ engagement, starting, onClick, onStart }: EngagementCardProps) {
  const targetType = (engagement.target_type ?? 'web') as TargetType
  const label = engagement.target_path ?? engagement.target_url

  return (
    <button
      onClick={onClick}
      className="text-left p-4 bg-gray-900 border border-gray-800 rounded-lg hover:border-orange-500 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 mr-2 min-w-0">
          <div className="flex items-center gap-1 mb-0.5">
            <span className="text-xs text-gray-500">{TARGET_TYPE_ICONS[targetType]} {TARGET_TYPE_LABELS[targetType]}</span>
          </div>
          <h3 className="font-medium text-gray-100 truncate text-sm">{label}</h3>
        </div>
        <span className={`text-xs px-2 py-1 rounded-full whitespace-nowrap ${STATUS_COLORS[engagement.status]}`}>
          {engagement.status}
        </span>
      </div>
      <div className="text-xs text-gray-500 mb-3">{new Date(engagement.created_at).toLocaleString()}</div>

      {engagement.status === 'pending' && (
        <button
          onClick={onStart}
          disabled={starting}
          className="w-full py-1.5 text-xs bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 text-white rounded font-medium transition-colors"
        >
          {starting ? 'Starting...' : '▶ Start Pentest'}
        </button>
      )}
      {engagement.status === 'running' && (
        <div className="flex items-center gap-1.5 text-xs text-green-400">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          Running — click to monitor
        </div>
      )}
    </button>
  )
}
