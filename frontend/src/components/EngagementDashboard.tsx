import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import type { Engagement, EngagementStatus, TargetType } from '../types'

const STATUS: Record<EngagementStatus, { color: string; label: string }> = {
  running:        { color: 'var(--running)', label: '● RUNNING' },
  complete:       { color: 'var(--complete)', label: '✓ COMPLETE' },
  paused_at_gate: { color: 'var(--gate)',    label: '⊘ GATE' },
  pending:        { color: 'var(--pending)', label: '○ PENDING' },
  aborted:        { color: 'var(--aborted)', label: '✕ ABORTED' },
}

const TYPE: Record<TargetType, string> = {
  web: 'web',
  local_codebase: 'code',
  binary: 'binary',
}

const COLS = '110px 1fr 70px 90px 65px 90px'

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
    <div style={{ padding: '20px 24px' }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '12px', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
          <span style={{ color: 'var(--accent)', fontSize: '13px', letterSpacing: '3px', fontWeight: 700 }}>FORGE</span>
          <span style={{ color: 'var(--text-label)', fontSize: '9px', letterSpacing: '1px' }}>v14.0 // offensive security platform</span>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          style={{ background: 'transparent', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: '9px', padding: '3px 12px', letterSpacing: '1px' }}
        >
          {showForm ? '× CANCEL' : '+ NEW'}
        </button>
      </div>

      {/* New engagement form */}
      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{ marginBottom: '16px', padding: '12px', border: '1px solid var(--border)', borderLeft: '2px solid var(--accent)', background: 'var(--surface)' }}
        >
          <div style={{ color: 'var(--text-label)', fontSize: '9px', letterSpacing: '1px', marginBottom: '6px' }}>NEW ENGAGEMENT</div>

          <div style={{ marginBottom: '8px' }}>
            <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>TARGET_TYPE</div>
            <div style={{ display: 'flex', gap: '4px' }}>
              {(['web', 'local_codebase', 'binary'] as TargetType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTargetType(t)}
                  style={{
                    flex: 1, padding: '4px 0', fontSize: '8px', letterSpacing: '1px',
                    background: targetType === t ? 'var(--accent-bg)' : 'transparent',
                    border: `1px solid ${targetType === t ? 'var(--accent)' : 'var(--border)'}`,
                    color: targetType === t ? 'var(--accent)' : 'var(--text-secondary)',
                  }}
                >
                  {TYPE[t].toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {targetType === 'web' ? (
            <div style={{ marginBottom: '8px' }}>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>TARGET_URL</div>
              <input
                type="url"
                required
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                placeholder="https://target.example.com"
                style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: '10px', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
          ) : (
            <div style={{ marginBottom: '8px' }}>
              <div style={{ color: 'var(--text-label)', fontSize: '8px', letterSpacing: '1px', marginBottom: '4px' }}>
                {targetType === 'binary' ? 'BINARY_PATH' : 'CODEBASE_PATH'}
              </div>
              <input
                type="text"
                required
                value={targetPath}
                onChange={(e) => setTargetPath(e.target.value)}
                placeholder={targetType === 'binary' ? '/path/to/binary' : '/Users/you/project'}
                style={{ width: '100%', padding: '5px 8px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: '10px', outline: 'none', boxSizing: 'border-box' }}
              />
            </div>
          )}

          {error && <div style={{ color: 'var(--crit)', fontSize: '9px', marginBottom: '6px' }}>{error}</div>}

          <button
            type="submit"
            disabled={submitting}
            style={{ width: '100%', padding: '6px 0', background: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: '9px', letterSpacing: '1px', opacity: submitting ? 0.5 : 1 }}
          >
            {submitting ? 'CREATING...' : '▶ CREATE ENGAGEMENT'}
          </button>
        </form>
      )}

      {/* Table header */}
      {engagements.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', color: 'var(--text-label)', fontSize: '9px', letterSpacing: '1px', borderBottom: '1px solid var(--border)', paddingBottom: '4px', marginBottom: '2px' }}>
          <span>STATUS</span>
          <span>TARGET</span>
          <span>TYPE</span>
          <span>FINDINGS</span>
          <span>DATE</span>
          <span></span>
        </div>
      )}

      {/* Rows */}
      {engagements.length === 0 ? (
        <div style={{ color: 'var(--text-dim)', fontSize: '9px', padding: '20px 0' }}>
          &gt; no engagements found. press + NEW to begin_
        </div>
      ) : (
        engagements.map((eng) => {
          const st = STATUS[eng.status]
          const label = eng.target_path ?? eng.target_url
          const date = new Date(eng.created_at).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' })
          return (
            <div
              key={eng.id}
              onClick={() => navigate(`/engagement/${eng.id}`)}
              style={{ display: 'grid', gridTemplateColumns: COLS, gap: '8px', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--border-deep)', cursor: 'pointer' }}
            >
              <span style={{ color: st.color, fontSize: '9px', letterSpacing: '1px' }}>{st.label}</span>
              <span style={{ color: 'var(--text-primary)', fontSize: '10px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: '9px' }}>{TYPE[eng.target_type]}</span>
              <span style={{ color: '#aaa', fontSize: '9px' }}>—</span>
              <span style={{ color: 'var(--text-dim)', fontSize: '9px' }}>{date}</span>
              <span>
                {eng.status === 'pending' ? (
                  <button
                    onClick={(e) => handleStart(e, eng)}
                    disabled={starting === eng.id}
                    style={{ background: 'transparent', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: '8px', padding: '2px 8px', letterSpacing: '1px' }}
                  >
                    {starting === eng.id ? '...' : '▶ LAUNCH'}
                  </button>
                ) : (
                  <span style={{ color: 'var(--accent-glow)', fontSize: '8px' }}>[view]</span>
                )}
              </span>
            </div>
          )
        })
      )}

      <div style={{ color: 'var(--accent-glow)', fontSize: '9px', marginTop: '10px' }}>
        {engagements.length} engagement(s) loaded_
      </div>
    </div>
  )
}
