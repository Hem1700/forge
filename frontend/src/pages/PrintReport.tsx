import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { engagementsApi } from '../api/engagements'
import type { Engagement, FindingDetail } from '../types'

export function PrintReport() {
  const { engagementId } = useParams<{ engagementId: string }>()
  const [engagement, setEngagement] = useState<Engagement | null>(null)
  const [findings, setFindings] = useState<FindingDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!engagementId) return
    Promise.all([
      engagementsApi.get(engagementId),
      engagementsApi.findings(engagementId),
    ])
      .then(([eng, fs]) => {
        setEngagement(eng)
        setFindings(fs as unknown as FindingDetail[])
      })
      .catch((err) => {
        console.error(err)
        setError('Failed to load report data.')
      })
      .finally(() => setLoading(false))
  }, [engagementId])

  if (loading) {
    return <div style={{ padding: '2rem', fontFamily: 'monospace' }}>Loading report…</div>
  }

  if (error) {
    return <div style={{ padding: '2rem', fontFamily: 'monospace', color: 'red' }}>{error}</div>
  }

  if (!engagement) {
    return <div style={{ padding: '2rem', fontFamily: 'monospace' }}>Engagement not found.</div>
  }

  const counts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  for (const f of findings) {
    const sev = f.severity as keyof typeof counts
    if (sev in counts) counts[sev]++
  }

  const severityOrder = ['critical', 'high', 'medium', 'low', 'info']
  const sorted = [...findings].sort(
    (a, b) => severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity)
  )

  return (
    <div className="print-report">
      <style>{`
        body { margin: 0; background: white; color: black; }
        .print-report {
          font-family: Georgia, 'Times New Roman', serif;
          font-size: 11pt;
          color: #000;
          background: #fff;
          max-width: 210mm;
          margin: 0 auto;
          padding: 20mm 20mm 20mm 20mm;
        }
        .report-header {
          border-bottom: 2px solid #000;
          padding-bottom: 1rem;
          margin-bottom: 1.5rem;
        }
        .report-header h1 {
          font-size: 20pt;
          font-weight: bold;
          margin: 0 0 0.5rem 0;
          letter-spacing: 0.05em;
        }
        .report-header p {
          margin: 0.2rem 0;
          font-size: 10pt;
        }
        .summary-table {
          border-collapse: collapse;
          margin: 0.5rem 0 1.5rem 0;
          font-size: 10pt;
        }
        .summary-table td, .summary-table th {
          border: 1px solid #999;
          padding: 4px 12px;
        }
        .summary-table th {
          background: #f0f0f0;
          font-weight: bold;
        }
        .finding {
          page-break-before: always;
          padding-top: 0.5rem;
        }
        .finding-header {
          border-bottom: 1px solid #000;
          padding-bottom: 0.5rem;
          margin-bottom: 1rem;
        }
        .finding-header h2 {
          font-size: 14pt;
          font-weight: bold;
          margin: 0 0 0.25rem 0;
        }
        .finding-header .meta {
          font-size: 9pt;
          color: #444;
        }
        .section-label {
          font-weight: bold;
          font-size: 10pt;
          margin: 1rem 0 0.25rem 0;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .section-body {
          font-size: 10pt;
          line-height: 1.5;
          margin: 0 0 0.5rem 0;
        }
        pre, code {
          font-family: 'Courier New', Courier, monospace;
          font-size: 8.5pt;
          background: #f5f5f5;
          border: 1px solid #ccc;
          padding: 0.75rem;
          white-space: pre-wrap;
          word-break: break-all;
          display: block;
          margin: 0.25rem 0 0.75rem 0;
          color: #000;
        }
        .verdict-badge {
          display: inline-block;
          font-weight: bold;
          font-size: 10pt;
          padding: 2px 8px;
          border: 1px solid #000;
        }
        @media print {
          body { background: white; }
          .print-report { padding: 0; max-width: 100%; }
          .finding { page-break-before: always; }
        }
      `}</style>

      {/* Report Header */}
      <div className="report-header">
        <h1>FORGE PENTEST REPORT</h1>
        <p><strong>Engagement:</strong> {engagement.target_url}</p>
        <p><strong>Generated:</strong> {new Date().toISOString().slice(0, 10)}</p>
        <p><strong>ID:</strong> {engagement.id}</p>
        <p><strong>Status:</strong> {engagement.status}</p>
        <p><strong>Total Findings:</strong> {findings.length} ({
          (['critical', 'high', 'medium', 'low', 'info'] as const)
            .filter(s => counts[s] > 0)
            .map(s => `${counts[s]} ${s.charAt(0).toUpperCase() + s.slice(1)}`)
            .join(', ')
        })</p>
      </div>

      {/* Severity Summary Table */}
      {findings.length > 0 && (
        <table className="summary-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            {severityOrder.filter(s => counts[s as keyof typeof counts] > 0).map(s => (
              <tr key={s}>
                <td>{s.charAt(0).toUpperCase() + s.slice(1)}</td>
                <td>{counts[s as keyof typeof counts]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {findings.length === 0 && (
        <p style={{ fontStyle: 'italic', color: '#666' }}>No findings recorded for this engagement.</p>
      )}

      {/* Findings */}
      {sorted.map((finding, idx) => (
        <div key={finding.id} className="finding" style={{ pageBreakBefore: idx === 0 ? 'auto' : 'always' }}>
          <div className="finding-header">
            <h2>
              FINDING {idx + 1} — {finding.vulnerability_class} [{finding.severity.toUpperCase()}]
            </h2>
            <div className="meta">
              Surface: {finding.affected_surface}
            </div>
          </div>

          {finding.title && (
            <>
              <div className="section-label">Title</div>
              <div className="section-body">{finding.title}</div>
            </>
          )}

          {finding.description && (
            <>
              <div className="section-label">Description</div>
              <div className="section-body">{finding.description}</div>
            </>
          )}

          {finding.evidence && (Array.isArray(finding.evidence) ? finding.evidence.length > 0 : !!finding.evidence) && (
            <>
              <div className="section-label">Evidence</div>
              <div className="section-body">
                {Array.isArray(finding.evidence)
                  ? finding.evidence.map((e, i) => <div key={i}>{typeof e === 'string' ? e : JSON.stringify(e)}</div>)
                  : String(finding.evidence)}
              </div>
            </>
          )}

          {finding.reproduction_steps && finding.reproduction_steps.length > 0 && (
            <>
              <div className="section-label">Reproduction Steps</div>
              <ol style={{ margin: '0 0 0.75rem 1.5rem', fontSize: '10pt', lineHeight: 1.5 }}>
                {finding.reproduction_steps.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
            </>
          )}

          {/* PoC Script */}
          {finding.poc_detail && (
            <>
              <div className="section-label">
                PoC Script [{finding.poc_detail.language || 'python'}]
              </div>
              {finding.poc_detail.notes && (
                <div className="section-body" style={{ fontSize: '9pt', fontStyle: 'italic' }}>
                  {finding.poc_detail.notes}
                </div>
              )}
              <pre>{finding.poc_detail.script || ''}</pre>
            </>
          )}

          {/* Exploit Script */}
          {finding.exploit_script && (
            <>
              <div className="section-label">
                Exploit Script [{finding.exploit_script.language || 'python'}]
              </div>
              <pre>{finding.exploit_script.script || ''}</pre>
            </>
          )}

          {/* Execution Result */}
          {finding.exploit_execution && (
            <>
              <div className="section-label">Execution Result</div>
              <div className="section-body">
                <strong>Verdict:</strong>{' '}
                <span className="verdict-badge">
                  {(finding.exploit_execution.override_verdict ||
                    finding.exploit_execution.verdict || 'UNKNOWN').toUpperCase()}
                  {' '}({Math.round((finding.exploit_execution.confidence || 0) * 100)}%)
                </span>
              </div>
              {finding.exploit_execution.reasoning && (
                <div className="section-body">
                  <strong>Reasoning:</strong> {finding.exploit_execution.reasoning}
                </div>
              )}
              {finding.exploit_execution.stdout && (
                <>
                  <div className="section-label">stdout</div>
                  <pre>{finding.exploit_execution.stdout}</pre>
                </>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  )
}
