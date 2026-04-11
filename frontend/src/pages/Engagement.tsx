import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import { useSwarmStream } from '../hooks/useSwarmStream'
import { SwarmMonitor } from '../components/SwarmMonitor'
import { HumanGate } from '../components/HumanGate'
import { FindingsPanel } from '../components/FindingsPanel'
import { ReportViewer } from '../components/ReportViewer'
import type { EngagementStatus } from '../types'

const STATUS_COLORS: Record<EngagementStatus, string> = {
  pending: 'bg-gray-700 text-gray-200',
  running: 'bg-green-700 text-green-100',
  paused_at_gate: 'bg-yellow-700 text-yellow-100',
  complete: 'bg-blue-700 text-blue-100',
  aborted: 'bg-red-700 text-red-100',
}

export function Engagement() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const setActiveEngagement = useEngagementStore((s) => s.setActiveEngagement)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)

  useEffect(() => {
    if (!id) return
    engagementsApi.get(id).then(setActiveEngagement).catch(console.error)
    return () => setActiveEngagement(null)
  }, [id, setActiveEngagement])

  useSwarmStream(id ?? null)

  if (!activeEngagement) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-400 flex items-center justify-center">
        Loading engagement…
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => navigate(-1)}
          className="text-gray-400 hover:text-gray-100 transition-colors"
        >
          ← Back
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-gray-100 truncate">{activeEngagement.target_url}</h1>
        </div>
        <span className={`text-xs px-2 py-1 rounded-full ${STATUS_COLORS[activeEngagement.status]}`}>
          {activeEngagement.status}
        </span>
      </header>

      <main className="px-6 py-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <SwarmMonitor />
        </div>
        <div className="flex flex-col gap-4">
          <HumanGate engagement={activeEngagement} />
          <FindingsPanel />
        </div>
      </main>

      <div className="px-6 pb-8">
        <ReportViewer engagementId={activeEngagement.id} />
      </div>
    </div>
  )
}
