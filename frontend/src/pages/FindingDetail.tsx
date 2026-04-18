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

const VERDICT_STYLES: Record<string, string> = {
  confirmed: 'bg-green-900 text-green-300 border border-green-700',
  failed: 'bg-red-900 text-red-300 border border-red-700',
  inconclusive: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
}

const VERDICT_ICONS: Record<string, string> = {
  confirmed: '✅',
  failed: '❌',
  inconclusive: '⚠️',
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
  const [scriptLoading, setScriptLoading] = useState(false)
  const [executeLoading, setExecuteLoading] = useState(false)
  const [showExecuteModal, setShowExecuteModal] = useState(false)
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
    setError(null)
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
    setError(null)
    try {
      const exploit = await findingsApi.generateExploit(findingId)
      setFinding((prev) => (prev ? { ...prev, exploit_detail: exploit } : prev))
    } catch {
      setError('Failed to generate exploit. Check backend logs.')
    } finally {
      setExploitLoading(false)
    }
  }

  async function handleGenerateExploitScript() {
    if (!findingId) return
    setScriptLoading(true)
    setError(null)
    try {
      const script = await findingsApi.generateExploitScript(findingId)
      setFinding((prev) => (prev ? { ...prev, exploit_script: script } : prev))
    } catch {
      setError('Failed to generate exploit script. Check backend logs.')
    } finally {
      setScriptLoading(false)
    }
  }

  async function handleExecuteExploit() {
    if (!findingId) return
    setShowExecuteModal(false)
    setExecuteLoading(true)
    setError(null)
    try {
      const execution = await findingsApi.executeExploit(findingId)
      setFinding((prev) => (prev ? { ...prev, exploit_execution: execution } : prev))
    } catch {
      setError('Execution failed. Check backend logs.')
    } finally {
      setExecuteLoading(false)
    }
  }

  async function handleOverrideVerdict(verdict: string) {
    if (!findingId) return
    try {
      const updated = await findingsApi.overrideVerdict(findingId, verdict)
      setFinding((prev) => (prev ? { ...prev, exploit_execution: updated } : prev))
    } catch {
      setError('Failed to override verdict.')
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

  const activeVerdict =
    finding.exploit_execution?.override_verdict ?? finding.exploit_execution?.verdict

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Execute confirmation modal */}
      {showExecuteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="bg-gray-900 border border-red-800 rounded-lg p-6 max-w-md w-full mx-4 space-y-4">
            <h3 className="text-lg font-semibold text-red-400">⚠ Live Exploit Execution</h3>
            <p className="text-sm text-gray-300">
              This will run a fully weaponized exploit against:
            </p>
            <p className="font-mono text-sm text-orange-300 bg-gray-800 px-3 py-2 rounded">
              {location}
            </p>
            {finding.exploit_script && (
              <p className="text-xs text-gray-400">
                Impact: {finding.exploit_script.impact_achieved}
              </p>
            )}
            <p className="text-xs text-yellow-400">
              Only proceed on systems you own or have explicit written permission to test.
            </p>
            <div className="flex gap-3 pt-2">
              <button
                onClick={handleExecuteExploit}
                className="flex-1 px-4 py-2 bg-red-700 hover:bg-red-600 text-white rounded-md font-medium text-sm transition-colors"
              >
                Execute
              </button>
              <button
                onClick={() => setShowExecuteModal(false)}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md font-medium text-sm transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

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
              <div>
                <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
                  Walkthrough
                </p>
                <ExploitWalkthrough steps={finding.exploit_detail.walkthrough} />
              </div>
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
                    Attack Path
                  </p>
                  <AttackPathDiagram source={finding.exploit_detail.attack_path_mermaid} />
                </div>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div className="bg-gray-800 rounded p-2">
                    <div className="text-gray-500 text-xs mb-1">Difficulty</div>
                    <div
                      className={`font-semibold capitalize ${
                        DIFFICULTY_COLORS[finding.exploit_detail.difficulty] ?? 'text-gray-300'
                      }`}
                    >
                      {finding.exploit_detail.difficulty}
                    </div>
                  </div>
                  <div className="bg-gray-800 rounded p-2 col-span-2">
                    <div className="text-gray-500 text-xs mb-1">Impact</div>
                    <div className="text-gray-200 text-xs">{finding.exploit_detail.impact}</div>
                  </div>
                </div>
                {finding.exploit_detail.prerequisites.length > 0 && (
                  <div>
                    <div className="text-gray-500 text-xs mb-1">Prerequisites</div>
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
              <p className="text-gray-500 text-sm">No exploit intelligence generated yet.</p>
              <button
                onClick={handleGenerateExploit}
                disabled={exploitLoading}
                className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-md font-medium transition-colors text-sm"
              >
                {exploitLoading ? 'Generating\u2026' : 'Generate Exploit'}
              </button>
              {error && <p className="text-red-400 text-xs">{error}</p>}
            </div>
          )}
        </div>

        {/* PoC Script */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
          <h2 className="font-semibold text-gray-100 mb-5 text-base">PoC Script</h2>
          {finding.poc_detail ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">Script</p>
                <PoCScript poc={finding.poc_detail} />
              </div>
              <div>
                <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">Exploit Sequence</p>
                <ExploitSequenceDiagram source={finding.poc_detail.sequence_diagram} />
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center py-10 gap-3">
              <p className="text-gray-500 text-sm">No PoC script generated yet.</p>
              <button
                onClick={handleGeneratePoC}
                disabled={pocLoading}
                className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-md font-medium transition-colors text-sm"
              >
                {pocLoading ? 'Generating\u2026' : 'Generate PoC'}
              </button>
              {error && <p className="text-red-400 text-xs">{error}</p>}
            </div>
          )}
        </div>

        {/* Live Exploitation */}
        <div className="bg-gray-900 border border-red-900/50 rounded-lg p-5">
          <h2 className="font-semibold text-gray-100 mb-5 text-base flex items-center gap-2">
            Live Exploitation
            <span className="text-xs px-2 py-0.5 rounded-full bg-red-900 text-red-300 font-normal">
              authorized use only
            </span>
          </h2>

          {/* Step 1: Exploit Script */}
          <div className="mb-6">
            <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
              Step 1 — Weaponized Script
            </p>

            {finding.exploit_script ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-300 font-mono">
                    {finding.exploit_script.language}
                  </span>
                  <span className="font-mono text-sm text-gray-200">
                    {finding.exploit_script.filename}
                  </span>
                  <button
                    onClick={() => {
                      const blob = new Blob([finding.exploit_script!.script], { type: 'text/plain' })
                      const url = URL.createObjectURL(blob)
                      const a = document.createElement('a')
                      a.href = url
                      a.download = finding.exploit_script!.filename
                      a.click()
                      URL.revokeObjectURL(url)
                    }}
                    className="ml-auto text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded transition-colors"
                  >
                    Download
                  </button>
                </div>

                <pre className="text-xs font-mono text-gray-300 bg-gray-950 p-3 rounded overflow-x-auto max-h-64 border border-gray-800">
                  {finding.exploit_script.script}
                </pre>

                {finding.exploit_script.setup.length > 0 && (
                  <p className="text-xs text-gray-500">
                    Setup: <span className="font-mono text-gray-400">{finding.exploit_script.setup.join(', ')}</span>
                  </p>
                )}

                <div className="text-xs text-gray-500 space-y-1">
                  <p>Expected: <span className="text-gray-400">{finding.exploit_script.expected_output}</span></p>
                  <p>Impact: <span className="text-red-400">{finding.exploit_script.impact_achieved}</span></p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-start gap-2">
                <button
                  onClick={handleGenerateExploitScript}
                  disabled={scriptLoading}
                  className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-md font-medium transition-colors text-sm"
                >
                  {scriptLoading ? 'Generating\u2026' : 'Generate Exploit Script'}
                </button>
              </div>
            )}
          </div>

          {/* Step 2: Execute */}
          {finding.exploit_script && (
            <div>
              <p className="text-xs font-semibold text-orange-400 uppercase tracking-widest mb-3">
                Step 2 — Execute Against Target
              </p>

              {finding.exploit_execution ? (
                <div className="space-y-4">
                  {/* Verdict badge */}
                  <div className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-semibold ${
                    VERDICT_STYLES[activeVerdict ?? 'inconclusive']
                  }`}>
                    {VERDICT_ICONS[activeVerdict ?? 'inconclusive']}{' '}
                    {(activeVerdict ?? 'inconclusive').toUpperCase()}{' '}
                    ({Math.round((finding.exploit_execution.confidence) * 100)}%)
                    {finding.exploit_execution.override_verdict && (
                      <span className="text-xs font-normal opacity-70 ml-1">manually overridden</span>
                    )}
                  </div>

                  {/* Reasoning */}
                  <p className="text-sm text-gray-300">{finding.exploit_execution.reasoning}</p>

                  {/* Stdout */}
                  {finding.exploit_execution.stdout && (
                    <div>
                      <p className="text-xs text-gray-500 mb-1">Output</p>
                      <pre className="text-xs font-mono text-green-300 bg-gray-950 p-3 rounded overflow-x-auto max-h-48 border border-gray-800">
                        {finding.exploit_execution.stdout}
                      </pre>
                    </div>
                  )}

                  {/* Override */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">Override verdict:</span>
                    {(['confirmed', 'failed', 'inconclusive'] as const).map((v) => (
                      <button
                        key={v}
                        onClick={() => handleOverrideVerdict(v)}
                        className={`text-xs px-2 py-1 rounded transition-colors ${
                          activeVerdict === v
                            ? 'bg-gray-600 text-white'
                            : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
                        }`}
                      >
                        {v}
                      </button>
                    ))}
                  </div>

                  {finding.exploit_execution.timed_out && (
                    <p className="text-xs text-yellow-400">⚠ Execution timed out</p>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-start gap-2">
                  <button
                    onClick={() => setShowExecuteModal(true)}
                    disabled={executeLoading}
                    className="px-4 py-2 bg-red-700 hover:bg-red-600 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-md font-semibold transition-colors text-sm"
                  >
                    {executeLoading ? 'Executing\u2026' : '⚠ Execute Against Target'}
                  </button>
                  {error && <p className="text-red-400 text-xs">{error}</p>}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Evidence + Description */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="font-semibold text-gray-100 mb-3 text-sm">Evidence</h3>
            <pre className="text-xs font-mono text-gray-300 bg-gray-800 p-3 rounded overflow-x-auto whitespace-pre-wrap max-h-60">
              {evidence || 'No evidence captured.'}
            </pre>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="font-semibold text-gray-100 mb-3 text-sm">Description</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              {finding.description || 'No description provided.'}
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
