import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/auth'

const ROLE_COLOR: Record<string, string> = {
  viewer:      'var(--text-secondary)',
  analyst:     'var(--accent)',
  admin:       'var(--gate)',
  super_admin: 'var(--crit)',
}

function decodeInviteClaims(token: string): { org_name: string; role: string } | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (payload.type === 'invite' && payload.org_name && payload.role) {
      return { org_name: payload.org_name, role: payload.role }
    }
  } catch { /* ignored */ }
  return null
}

export function Login() {
  const [searchParams] = useSearchParams()
  const inviteToken = searchParams.get('invite') ?? undefined
  const inviteClaims = inviteToken ? decodeInviteClaims(inviteToken) : null

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('')
  const [position, setPosition] = useState('')
  const [mode, setMode] = useState<'login' | 'register'>(inviteToken ? 'register' : 'login')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setToken } = useAuthStore()

  // When arriving via invite link, jump straight to register
  useEffect(() => {
    if (inviteToken) setMode('register')
  }, [inviteToken])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      let data: { access_token: string }
      if (mode === 'login') {
        data = await authApi.login(email, password)
      } else {
        data = await authApi.register(email, password, orgName, position || undefined, inviteToken)
      }
      setToken(data.access_token)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = {
    width: '100%',
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: 'var(--fs-md)',
    padding: '6px 10px',
    outline: 'none',
    boxSizing: 'border-box' as const,
  }

  const field = (label: string, type: string, value: string, onChange: (v: string) => void, placeholder?: string) => (
    <div>
      <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={inputStyle}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
      />
    </div>
  )

  const submitDisabled = loading || (mode === 'register' && !inviteToken && !orgName.trim())

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: '32px', width: '100%', maxWidth: '380px' }}>
        <div style={{ marginBottom: '24px' }}>
          <div style={{ color: 'var(--accent)', fontSize: 'var(--fs-lg)', fontWeight: 700, letterSpacing: '3px' }}>FORGE</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', marginTop: '4px' }}>
            {mode === 'login' ? 'sign in to your account' : 'create your account'}
          </div>
        </div>

        {/* Invite banner */}
        {inviteClaims && mode === 'register' && (
          <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderLeft: `2px solid ${ROLE_COLOR[inviteClaims.role] ?? 'var(--accent)'}`, padding: '8px 12px', marginBottom: '16px' }}>
            <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '2px' }}>INVITED TO JOIN</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-md)' }}>{inviteClaims.org_name}</span>
              <span style={{ color: ROLE_COLOR[inviteClaims.role] ?? 'var(--text-secondary)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>as {inviteClaims.role}</span>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {field('EMAIL', 'email', email, setEmail)}
          {field('PASSWORD', 'password', password, setPassword)}

          {mode === 'register' && !inviteToken && (
            field('ORGANISATION', 'text', orgName, setOrgName, 'e.g. Acme Corp')
          )}

          {mode === 'register' && (
            field('POSITION (optional)', 'text', position, setPosition, 'e.g. Security Engineer')
          )}

          {error && <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-sm)' }}>{error}</div>}

          <button
            type="submit"
            disabled={submitDisabled}
            style={{ width: '100%', padding: '8px 0', background: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', opacity: submitDisabled ? 0.5 : 1 }}
          >
            {loading ? '...' : mode === 'login' ? '▶ SIGN IN' : '▶ CREATE ACCOUNT'}
          </button>
        </form>

        {!inviteToken && (
          <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', textAlign: 'center', marginTop: '20px' }}>
            {mode === 'login' ? (
              <>
                no account?{' '}
                <button onClick={() => { setMode('register'); setError(null) }} style={{ background: 'transparent', border: 'none', color: 'var(--accent)', fontSize: 'var(--fs-sm)', padding: 0 }}>
                  register
                </button>
              </>
            ) : (
              <>
                have an account?{' '}
                <button onClick={() => { setMode('login'); setError(null) }} style={{ background: 'transparent', border: 'none', color: 'var(--accent)', fontSize: 'var(--fs-sm)', padding: 0 }}>
                  sign in
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
