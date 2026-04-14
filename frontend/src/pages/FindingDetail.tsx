import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { findingsApi } from '../api/findings'
import { ExploitWalkthrough } from '../components/ExploitWalkthrough'
import { AttackPathDiagram } from '../components/AttackPathDiagram'
import { PoCScript } from '../components/PoCScript'
import { ExploitSequenceDiagram } from '../components/ExploitSequenceDiagram'
import type { FindingDetail, Severity } from '../types'

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: 'bg-red-700 text-red-100',
  high: 'bg-orange-700 text-orange-100',
  medium: 'bg-yellow-700 text-yellow-100',
  low: 'bg-blue-700 text-blue-100',
  info: 'bg-gray-700 text-gray-200',
}

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: 'text-red-400',
  medium: 'text-yellow-400',
  hard: 'text-green-400',
}

export function FindingDetailPage() {
  const { engagementId, findingId } = useParams<{
    engagementId: string
    findingId: string
  }>()
  const navigate = useNavigate()
  const [finding, setFinding] = useState<FindingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [exploitLoading, setExploitLoading] = useState(false)
  const [pocLoading, setPocLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!findingId) return
    findingsApi
      .get(findingId)
      .then(setFinding)
      .catch(() => setError('Finding not found'))
      .finally(() => setLoading(false))
  }, [findingId])

  async function handleGeneratePoC() {
    if (!findingId) return
    setPocLoading(true)
    try {
      const poc = await findingsApi.generatePoC(findingId)
      setFinding((prev) => (prev ? { ...prev, poc_detail: poc } : prev))
    } catch {
      setError('Failed to generate PoC. Check backend logs.')
    } finally {
      setPocLoading(false)
    }
  }

  async function handleGenerateExploit() {
    if (!findingId) return
    setExploitLoading(true)
    try {
      const exploit = await findingsApi.generateExploit(findingId)
      setFinding((prev) => (prev ? { ...prev, exploit_detail: exploit } : prev))
    } catch {
      setError('Failed to generate exploit. Check backend logs.')
    } finally {
      setExploitLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-400 flex items-center justify-center">
        Loading finding...
      </div>
    )
  }

  if (error || !finding) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-400 flex items-center justify-center">
        {error || 'Finding not found'}
      </div>
    )
  }

  const vulnClass =
    finding.vulnerability_class ?? finding.attack_class ?? finding.title
  const location = finding.affected_surface ?? finding.endpoint ?? ''
  const evidence = Array.isArray(finding.evidence)
    ? finding.evidence.join('\n')
    : (finding.evidence ?? '')

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
        <button
          onClick={() => navigate(`/engagement/${engagementId}`)}
          className="text-gray-400 hover:text-gray-100 transition-colors"
        >
          &larr; Back to Engagement
        </button>
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <span
            className={`text-xs px-2 py-1 rounded-full flex-shrink-0 ${
              SEVERITY_COLORS[finding.severity]
            }`}
          >
            {finding.severity.toUpperCase()}
          </span>
          <h1 className="text-lg font-semibold text-gray-100 truncate">
            {vulnClass}
          </h1>
        </div>
        <div className="text-sm text-gray-400 flex-shrink-0">
          Confidence: {(finding.confidence_score * 100).toFixed(0)}%
        </div>
      </header>

      <main className="px-6 py-6 space-y-6 max-w-7xl mx-auto">
        {/* Location */}
        <p className="text-sm text-gray-400">
          Location:{' '}
          <span className="font-mono text-gray-200">{location || '\u2014'}</span>
        </p>

        {/* Exploit Intelligence */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h2 className="font-semibold text-gray-100 mb-5 text-base">
            Exploit Intelligence
          </h2>

          {finding.exploit_detail ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left: walkthrough */}
              <div>
                <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
                  Walkthrough
                </p>
                <ExploitWalkthrough steps={finding.exploit_detail.walkthrough} />
              </div>

              {/* Right: diagram + metadata */}
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
                    Attack Path
                  </p>
                  <AttackPathDiagram
                    source={finding.exploit_detail.attack_path_mermaid}
                  />
                </div>

                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div className="bg-gray-800 rounded p-2">
                    <div className="text-gray-500 text-xs mb-1">Difficulty</div>
                    <div
                      className={`font-semibold capitalize ${
                        DIFFICULTY_COLORS[finding.exploit_detail.difficulty] ??
                        'text-gray-300'
                      }`}
                    >
                      {finding.exploit_detail.difficulty}
                    </div>
                  </div>
                  <div className="bg-gray-800 rounded p-2 col-span-2">
                    <div className="text-gray-500 text-xs mb-1">Impact</div>
                    <div className="text-gray-200 text-xs">
                      {finding.exploit_detail.impact}
                    </div>
                  </div>
                </div>

                {finding.exploit_detail.prerequisites.length > 0 && (
                  <div>
                    <div className="text-gray-500 text-xs mb-1">
                      Prerequisites
                    </div>
                    <ul className="list-disc list-inside text-xs text-gray-300 space-y-0.5">
                      {finding.exploit_detail.prerequisites.map((p, i) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center py-10 gap-3">
              <p className="text-gray-500 text-sm">
                No exploit intelligence generated yet.
              </p>
              <button
                onClick={handleGenerateExploit}
                disabled={exploitLoading}
                className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-md font-medium transition-colors text-sm"
              >
                {exploitLoading ? 'Generating\u2026' : 'Generate Exploit'}
              </button>
              {error && (
                <p className="text-red-400 text-xs">{error}</p>
              )}
            </div>
          )}
        </div>

        {/* PoC Script */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h2 className="font-semibold text-gray-100 mb-5 text-base">
            PoC Script
          </h2>

          {finding.poc_detail ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
                  Script
                </p>
                <PoCScript poc={finding.poc_detail} />
              </div>
              <div>
                <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
                  Exploit Sequence
                </p>
                <ExploitSequenceDiagram source={finding.poc_detail.sequence_diagram} />
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center py-10 gap-3">
              <p className="text-gray-500 text-sm">
                No PoC script generated yet.
              </p>
              <button
                onClick={handleGeneratePoC}
                disabled={pocLoading}
                className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-md font-medium transition-colors text-sm"
              >
                {pocLoading ? 'Generating…' : 'Generate PoC'}
              </button>
            </div>
          )}
        </div>

        {/* Evidence + Description */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="font-semibold text-gray-100 mb-3 text-sm">
              Evidence
            </h3>
            <pre className="text-xs font-mono text-gray-300 bg-gray-800 p-3 rounded overflow-x-auto whitespace-pre-wrap max-h-60">
              {evidence || 'No evidence captured.'}
            </pre>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="font-semibold text-gray-100 mb-3 text-sm">
              Description
            </h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              {finding.description || 'No description provided.'}
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
