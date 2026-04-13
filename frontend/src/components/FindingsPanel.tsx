import { Link } from 'react-router-dom'
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
    : findings

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h3 className="font-semibold text-gray-100 mb-4">Findings ({filtered.length})</h3>

      {filtered.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">No findings yet</p>
      ) : (
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-900">
              <tr className="text-left text-gray-400 border-b border-gray-800">
                <th className="pb-2 pr-2">Severity</th>
                <th className="pb-2 pr-2">Vulnerability</th>
                <th className="pb-2 pr-2">Location</th>
                <th className="pb-2">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((f) => {
                const vulnClass = f.vulnerability_class ?? f.attack_class ?? f.title
                const location = f.affected_surface ?? f.endpoint ?? ''
                return (
                  <tr key={f.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer">
                    <td className="py-2 pr-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${SEVERITY_COLORS[f.severity]}`}>
                        {f.severity}
                      </span>
                    </td>
                    <td className="py-2 pr-2 text-gray-200 max-w-[180px] truncate">
                      <Link
                        to={`/engagements/${f.engagement_id}/findings/${f.id}`}
                        className="hover:text-orange-400 transition-colors"
                      >
                        {vulnClass}
                      </Link>
                    </td>
                    <td className="py-2 pr-2 text-gray-400 font-mono text-xs truncate max-w-[160px]">
                      {location}
                    </td>
                    <td className="py-2 text-gray-300 text-xs">{(f.confidence_score * 100).toFixed(0)}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
