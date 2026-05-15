import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/auth'

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('')
  const [position, setPosition] = useState('')
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setToken } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      let data: { access_token: string }
      if (mode === 'login') {
        data = await authApi.login(email, password)
      } else {
        data = await authApi.register(email, password, orgName, position || undefined)
      }
      setToken(data.access_token)
      navigate('/')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  const field = (
    label: string,
    type: string,
    value: string,
    onChange: (v: string) => void,
    placeholder?: string,
  ) => (
    <div>
      <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>
        {label}
      </div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', padding: '6px 10px', outline: 'none', boxSizing: 'border-box' }}
        onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
        onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
      />
    </div>
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: '32px', width: '100%', maxWidth: '380px' }}>
        <div style={{ marginBottom: '24px' }}>
          <div style={{ color: 'var(--accent)', fontSize: 'var(--fs-lg)', fontWeight: 700, letterSpacing: '3px' }}>FORGE</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', marginTop: '4px' }}>
            {mode === 'login' ? 'sign in to your account' : 'create your account'}
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {field('EMAIL', 'email', email, setEmail)}
          {field('PASSWORD', 'password', password, setPassword)}

          {mode === 'register' && (
            <>
              {field('ORGANISATION', 'text', orgName, setOrgName, 'e.g. Acme Corp')}
              {field('POSITION (optional)', 'text', position, setPosition, 'e.g. Security Engineer')}
            </>
          )}

          {error && (
            <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-sm)' }}>{error}</div>
          )}

          <button
            type="submit"
            disabled={loading || (mode === 'register' && !orgName.trim())}
            style={{ width: '100%', padding: '8px 0', background: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', opacity: (loading || (mode === 'register' && !orgName.trim())) ? 0.5 : 1 }}
          >
            {loading ? '...' : mode === 'login' ? '▶ SIGN IN' : '▶ CREATE ACCOUNT'}
          </button>
        </form>

        <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', textAlign: 'center', marginTop: '20px' }}>
          {mode === 'login' ? (
            <>
              no account?{' '}
              <button
                onClick={() => { setMode('register'); setError(null) }}
                style={{ background: 'transparent', border: 'none', color: 'var(--accent)', fontSize: 'var(--fs-sm)', padding: 0 }}
              >
                register
              </button>
            </>
          ) : (
            <>
              have an account?{' '}
              <button
                onClick={() => { setMode('login'); setError(null) }}
                style={{ background: 'transparent', border: 'none', color: 'var(--accent)', fontSize: 'var(--fs-sm)', padding: 0 }}
              >
                sign in
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
