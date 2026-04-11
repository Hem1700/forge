import { useEngagementStore } from '../store/engagement'
import type { Severity } from '../types'

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: 'bg-red-700 text-red-100',
  high: 'bg-orange-700 text-orange-100',
  medium: 'bg-yellow-700 text-yellow-100',
  low: 'bg-blue-700 text-blue-100',
  info: 'bg-gray-700 text-gray-200',
}

export function FindingsPanel() {
  const findings = useEngagementStore((s) => s.findings)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)

  const filtered = activeEngagement
    ? findings.filter((f) => f.engagement_id === activeEngagement.id)
    : []

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h3 className="font-semibold text-gray-100 mb-4">Findings ({filtered.length})</h3>

      {filtered.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">No findings yet</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-800">
                <th className="pb-2 pr-2">Severity</th>
                <th className="pb-2 pr-2">Title</th>
                <th className="pb-2 pr-2">Class</th>
                <th className="pb-2 pr-2">Endpoint</th>
                <th className="pb-2">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((f) => (
                <tr key={f.id} className="border-b border-gray-800/50">
                  <td className="py-2 pr-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${SEVERITY_COLORS[f.severity]}`}>
                      {f.severity}
                    </span>
                  </td>
                  <td className="py-2 pr-2 text-gray-200">{f.title}</td>
                  <td className="py-2 pr-2 text-gray-400">{f.attack_class}</td>
                  <td className="py-2 pr-2 text-gray-400 font-mono text-xs truncate max-w-[200px]">
                    {f.endpoint}
                  </td>
                  <td className="py-2 text-gray-300">{(f.confidence_score * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
