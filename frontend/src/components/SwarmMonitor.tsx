import { useEngagementStore } from '../store/engagement'
import type { SwarmEvent } from '../types'

const EVENT_COLORS: Record<SwarmEvent['type'], string> = {
  agent_started: 'bg-blue-700 text-blue-100',
  agent_completed: 'bg-green-700 text-green-100',
  finding_discovered: 'bg-orange-700 text-orange-100',
  gate_triggered: 'bg-yellow-700 text-yellow-100',
  campaign_complete: 'bg-purple-700 text-purple-100',
  ping: 'bg-gray-700 text-gray-300',
}

export function SwarmMonitor() {
  const events = useEngagementStore((s) => s.events)
  const agents = useEngagementStore((s) => s.agents)

  const recent = events.slice(0, 20)

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-100">Swarm Monitor</h3>
        {agents.length > 0 && (
          <span className="text-xs text-gray-400">
            {agents.length} active agent{agents.length === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {recent.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">Waiting for events...</p>
      ) : (
        <ul className="space-y-2 max-h-[500px] overflow-y-auto">
          {recent.map((event, idx) => (
            <li key={idx} className="text-xs border-l-2 border-gray-800 pl-3 py-1">
              <div className="flex items-center gap-2 mb-1">
                <span className={`px-2 py-0.5 rounded-full font-medium ${EVENT_COLORS[event.type]}`}>
                  {event.type}
                </span>
                <span className="text-gray-500">{new Date(event.timestamp).toLocaleTimeString()}</span>
              </div>
              <pre className="text-gray-400 font-mono text-[10px] whitespace-pre-wrap break-all">
                {JSON.stringify(event.payload, null, 0)}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
