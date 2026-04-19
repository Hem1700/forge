import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { findingsApi } from '../api/findings'
import { ExploitWalkthrough } from '../components/ExploitWalkthrough'
import { AttackPathDiagram } from '../components/AttackPathDiagram'
import { PoCScript } from '../components/PoCScript'
import { ExploitSequenceDiagram } from '../components/ExploitSequenceDiagram'
import type { FindingDetail, Severity } from '../types'

const SEV_COLOR: Record<Severity, string> = {
  critical: 'var(--crit)',
  high:     'var(--high)',
  medium:   'var(--medium)',
  low:      'var(--low)',
  info:     'var(--info)',
}

const SEV_DIM: Record<Severity, string> = {
  critical: 'var(--crit-dim)',
  high:     'var(--high-dim)',
  medium:   'var(--medium-dim)',
  low:      'var(--low-dim)',
  info:     'var(--pending-dim)',
}

const VERDICT_COLOR: Record<string, string> = {
  confirmed:   'var(--complete)',
  failed:      'var(--crit)',
  inconclusive:'var(--gate)',
}

const VERDICT_DIM: Record<string, string> = {
  confirmed:    'var(--complete-dim)',
  failed:       'var(--crit-dim)',
  inconclusive: 'var(--gate-dim)',
}

const DIFFICULTY_COLOR: Record<string, string> = {
  easy:   'var(--crit)',
  medium: 'var(--medium)',
  hard:   'var(--complete)',
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div style={{ color: 'var(--accent)', fontSize: 'var(--fs-xs)', letterSpacing: '2px', borderBottom: '1px solid var(--border)', paddingBottom: '6px', marginBottom: '10px' }}>
      {label}
    </div>
  )
}

function Panel({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <div style={{ border: '1px solid var(--border)', borderLeft: `2px solid ${accent ?? 'var(--border)'}`, background: 'var(--surface)', padding: '12px', marginBottom: '12px' }}>
      {children}
    </div>
  )
}

function ActionButton({ onClick, disabled, children, danger }: { onClick: () => void; disabled: boolean; children: React.ReactNode; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{ padding: '5px 14px', background: 'transparent', border: `1px solid ${danger ? 'var(--crit)' : 'var(--accent-dim)'}`, color: danger ? 'var(--crit)' : 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', opacity: disabled ? 0.5 : 1 }}
    >
      {children}
    </button>
  )
}

export function FindingDetailPage() {
  const { engagementId, findingId } = useParams<{ engagementId: string; findingId: string }>()
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
      setError('Failed to generate PoC.')
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
      setError('Failed to generate exploit.')
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
      setError('Failed to generate exploit script.')
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
      setError('Execution failed.')
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
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--fs-md)', letterSpacing: '1px' }}>
        &gt; loading finding_
      </div>
    )
  }

  if (error || !finding) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'var(--fs-md)' }}>
        {error || 'finding not found'}
      </div>
    )
  }

  const vulnClass = finding.vulnerability_class ?? finding.attack_class ?? finding.title
  const location = finding.affected_surface ?? finding.endpoint ?? ''
  const evidence = Array.isArray(finding.evidence) ? finding.evidence.join('\n') : (finding.evidence ?? '')
  const activeVerdict = finding.exploit_execution?.override_verdict ?? finding.exploit_execution?.verdict
  const sevColor = SEV_COLOR[finding.severity]

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      {/* Execute confirmation modal */}
      {showExecuteModal && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.8)' }}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--crit)', padding: '20px', maxWidth: '400px', width: '100%', margin: '0 16px' }}>
            <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-md)', letterSpacing: '1px', marginBottom: '10px' }}>⚠ LIVE EXPLOIT EXECUTION</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', marginBottom: '8px' }}>This will run a fully weaponized exploit against:</div>
            <div style={{ color: 'var(--high)', fontSize: 'var(--fs-sm)', background: 'var(--bg)', padding: '6px 10px', marginBottom: '8px', border: '1px solid var(--border)' }}>{location}</div>
            {finding.exploit_script && (
              <div style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-xs)', marginBottom: '8px' }}>Impact: {finding.exploit_script.impact_achieved}</div>
            )}
            <div style={{ color: 'var(--gate)', fontSize: 'var(--fs-xs)', marginBottom: '12px' }}>Only proceed on systems you own or have explicit written permission to test.</div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={handleExecuteExploit}
                style={{ flex: 1, padding: '6px 0', background: 'transparent', border: '1px solid var(--crit)', color: 'var(--crit)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', cursor: 'pointer' }}
              >
                EXECUTE
              </button>
              <button
                onClick={() => setShowExecuteModal(false)}
                style={{ flex: 1, padding: '6px 0', background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', cursor: 'pointer' }}
              >
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={() => navigate(`/engagement/${engagementId}`)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', padding: 0, cursor: 'pointer' }}
        >
          ← BACK
        </button>
        <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-sm)' }}>/</span>
        <span style={{ color: sevColor, fontSize: 'var(--fs-sm)', letterSpacing: '1px', border: `1px solid ${SEV_DIM[finding.severity]}`, padding: '2px 8px' }}>[{finding.severity.toUpperCase()}]</span>
        <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-base)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{vulnClass}</span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>CONF: {(finding.confidence_score * 100).toFixed(0)}%</span>
      </div>

      <div style={{ padding: '16px 24px', maxWidth: '1200px' }}>
        {/* Metadata grid */}
        <Panel accent={sevColor}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>SURFACE</div>
              <div style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-md)' }}>{location || '—'}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>CLASS</div>
              <div style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-md)' }}>{vulnClass}</div>
            </div>
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>VERDICT</div>
              <div style={{ color: activeVerdict ? VERDICT_COLOR[activeVerdict] : 'var(--text-secondary)', fontSize: 'var(--fs-md)', letterSpacing: '1px' }}>
                {activeVerdict?.toUpperCase() ?? 'PENDING'}
              </div>
            </div>
          </div>
        </Panel>

        {/* Description + Evidence */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
          <Panel>
            <SectionHeader label="DESCRIPTION" />
            <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', lineHeight: 1.6, margin: 0 }}>
              {finding.description || 'No description provided.'}
            </p>
          </Panel>
          <Panel>
            <SectionHeader label="EVIDENCE" />
            <pre style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', background: 'var(--bg)', padding: '8px', border: '1px solid var(--border)', overflowX: 'auto', maxHeight: '160px', margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {evidence || 'No evidence captured.'}
            </pre>
          </Panel>
        </div>

        {/* Exploit Intelligence */}
        <Panel>
          <SectionHeader label="EXPLOIT INTELLIGENCE" />
          {finding.exploit_detail ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '6px' }}>WALKTHROUGH</div>
                <ExploitWalkthrough steps={finding.exploit_detail.walkthrough} />
              </div>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '6px' }}>ATTACK PATH</div>
                <AttackPathDiagram source={finding.exploit_detail.attack_path_mermaid} />
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', marginTop: '8px' }}>
                  <div style={{ border: '1px solid var(--border)', padding: '6px' }}>
                    <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-tiny)', letterSpacing: '1px', marginBottom: '3px' }}>DIFFICULTY</div>
                    <div style={{ color: DIFFICULTY_COLOR[finding.exploit_detail.difficulty] ?? 'var(--text-primary)', fontSize: 'var(--fs-sm)', letterSpacing: '1px' }}>
                      {finding.exploit_detail.difficulty.toUpperCase()}
                    </div>
                  </div>
                  <div style={{ border: '1px solid var(--border)', padding: '6px', gridColumn: 'span 2' }}>
                    <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-tiny)', letterSpacing: '1px', marginBottom: '3px' }}>IMPACT</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>{finding.exploit_detail.impact}</div>
                  </div>
                </div>
                {finding.exploit_detail.prerequisites.length > 0 && (
                  <div style={{ marginTop: '8px' }}>
                    <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-tiny)', letterSpacing: '1px', marginBottom: '4px' }}>PREREQUISITES</div>
                    <ul style={{ margin: 0, paddingLeft: '14px', color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)' }}>
                      {finding.exploit_detail.prerequisites.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px', padding: '12px 0' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>&gt; no exploit intelligence generated yet_</div>
              <ActionButton onClick={handleGenerateExploit} disabled={exploitLoading}>
                {exploitLoading ? 'GENERATING...' : '▶ GENERATE EXPLOIT'}
              </ActionButton>
              {error && <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-xs)' }}>{error}</div>}
            </div>
          )}
        </Panel>

        {/* PoC Script */}
        <Panel>
          <SectionHeader label="POC SCRIPT" />
          {finding.poc_detail ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '6px' }}>SCRIPT</div>
                <PoCScript poc={finding.poc_detail} />
              </div>
              <div>
                <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '6px' }}>EXPLOIT SEQUENCE</div>
                <ExploitSequenceDiagram source={finding.poc_detail.sequence_diagram} />
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px', padding: '12px 0' }}>
              <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>&gt; no PoC script generated yet_</div>
              <ActionButton onClick={handleGeneratePoC} disabled={pocLoading}>
                {pocLoading ? 'GENERATING...' : '▶ GENERATE POC'}
              </ActionButton>
              {error && <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-xs)' }}>{error}</div>}
            </div>
          )}
        </Panel>

        {/* Live Exploitation */}
        <Panel accent="var(--crit)">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
            <span style={{ color: 'var(--crit)', fontSize: 'var(--fs-xs)', letterSpacing: '2px' }}>LIVE EXPLOITATION</span>
            <span style={{ color: 'var(--crit)', fontSize: 'var(--fs-tiny)', border: '1px solid var(--crit-dim)', padding: '1px 6px' }}>AUTHORIZED USE ONLY</span>
          </div>

          {/* Step 1: Weaponized Script */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '8px' }}>STEP 1 — WEAPONIZED SCRIPT</div>
            {finding.exploit_script ? (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', border: '1px solid var(--border)', padding: '1px 6px' }}>{finding.exploit_script.language}</span>
                  <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-sm)' }}>{finding.exploit_script.filename}</span>
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
                    style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', padding: '2px 8px', cursor: 'pointer' }}
                  >
                    ↓ DOWNLOAD
                  </button>
                </div>
                <pre style={{ color: 'var(--accent)', fontSize: 'var(--fs-xs)', background: 'var(--bg)', padding: '10px', border: '1px solid var(--accent-dim)', overflowX: 'auto', maxHeight: '200px', margin: '0 0 6px', fontFamily: 'inherit' }}>
                  {finding.exploit_script.script}
                </pre>
                <div style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-xs)' }}>
                  Expected: <span style={{ color: 'var(--text-secondary)' }}>{finding.exploit_script.expected_output}</span>
                  {' '} // Impact: <span style={{ color: 'var(--crit)' }}>{finding.exploit_script.impact_achieved}</span>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                <ActionButton onClick={handleGenerateExploitScript} disabled={scriptLoading}>
                  {scriptLoading ? 'GENERATING...' : '▶ GENERATE EXPLOIT SCRIPT'}
                </ActionButton>
              </div>
            )}
          </div>

          {/* Step 2: Execute */}
          {finding.exploit_script && (
            <div>
              <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '8px' }}>STEP 2 — EXECUTE AGAINST TARGET</div>
              {finding.exploit_execution ? (
                <div>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', border: `1px solid ${VERDICT_DIM[activeVerdict ?? 'inconclusive']}`, padding: '4px 10px', marginBottom: '8px' }}>
                    <span style={{ color: VERDICT_COLOR[activeVerdict ?? 'inconclusive'], fontSize: 'var(--fs-sm)', letterSpacing: '1px' }}>
                      {(activeVerdict ?? 'INCONCLUSIVE').toUpperCase()} ({Math.round(finding.exploit_execution.confidence * 100)}%)
                    </span>
                    {finding.exploit_execution.override_verdict && (
                      <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-tiny)' }}>// overridden</span>
                    )}
                  </div>
                  <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', marginBottom: '8px' }}>{finding.exploit_execution.reasoning}</p>
                  {finding.exploit_execution.stdout && (
                    <pre style={{ color: 'var(--complete)', fontSize: 'var(--fs-xs)', background: 'var(--bg)', padding: '8px', border: '1px solid var(--border)', overflowX: 'auto', maxHeight: '160px', margin: '0 0 8px', fontFamily: 'inherit' }}>
                      {finding.exploit_execution.stdout}
                    </pre>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-xs)' }}>override:</span>
                    {(['confirmed', 'failed', 'inconclusive'] as const).map((v) => (
                      <button
                        key={v}
                        onClick={() => handleOverrideVerdict(v)}
                        style={{ padding: '2px 8px', background: activeVerdict === v ? 'var(--border)' : 'transparent', border: `1px solid ${activeVerdict === v ? 'var(--accent)' : 'var(--border)'}`, color: activeVerdict === v ? 'var(--accent)' : 'var(--text-secondary)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', cursor: 'pointer' }}
                      >
                        {v}
                      </button>
                    ))}
                  </div>
                  {finding.exploit_execution.timed_out && (
                    <div style={{ color: 'var(--gate)', fontSize: 'var(--fs-xs)', marginTop: '6px' }}>⚠ execution timed out</div>
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}>
                  <ActionButton onClick={() => setShowExecuteModal(true)} disabled={executeLoading} danger>
                    {executeLoading ? 'EXECUTING...' : '⚠ EXECUTE AGAINST TARGET'}
                  </ActionButton>
                  {error && <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-xs)' }}>{error}</div>}
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
