import { useMemo } from 'react'
import { useEngagementStore } from '../store/engagement'
import type { Severity } from '../types'

interface ReportViewerProps {
  engagementId: string
}

const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

const SEVERITY_BAR_COLORS: Record<Severity, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-blue-500',
  info: 'bg-gray-500',
}

export function ReportViewer({ engagementId }: ReportViewerProps) {
  const findings = useEngagementStore((s) => s.findings)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)

  const scopedFindings = useMemo(
    () => findings.filter((f) => f.engagement_id === engagementId),
    [findings, engagementId]
  )

  const bySeverity = useMemo(() => {
    const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
    for (const f of scopedFindings) counts[f.severity]++
    return counts
  }, [scopedFindings])

  const maxCount = Math.max(...Object.values(bySeverity), 1)

  function handleExport() {
    const data = JSON.stringify(scopedFindings, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `forge-findings-${engagementId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-100">Report Summary</h3>
        <button
          onClick={handleExport}
          disabled={scopedFindings.length === 0}
          className="px-3 py-1.5 text-sm bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 text-white rounded-md font-medium transition-colors"
        >
          Export JSON
        </button>
      </div>

      {activeEngagement && (
        <div className="grid grid-cols-2 gap-4 mb-6 text-sm">
          <div>
            <div className="text-gray-500 text-xs mb-1">Status</div>
            <div className="text-gray-200">{activeEngagement.status}</div>
          </div>
          <div>
            <div className="text-gray-500 text-xs mb-1">Gate</div>
            <div className="text-gray-200">{activeEngagement.gate_status}</div>
          </div>
        </div>
      )}

      <div className="mb-2 text-sm text-gray-400">Total findings: {scopedFindings.length}</div>

      <div className="space-y-2">
        {SEVERITY_ORDER.map((sev) => {
          const count = bySeverity[sev]
          const width = (count / maxCount) * 100
          return (
            <div key={sev} className="flex items-center gap-3">
              <div className="w-20 text-xs text-gray-400 capitalize">{sev}</div>
              <div className="flex-1 h-5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={`h-full ${SEVERITY_BAR_COLORS[sev]} transition-all`}
                  style={{ width: `${width}%` }}
                />
              </div>
              <div className="w-8 text-right text-xs text-gray-300">{count}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
