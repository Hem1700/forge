import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BASE_URL } from '../api/client'
import { useAuthStore } from '../store/auth'

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setToken } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    const endpoint = mode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/register'
    try {
      const res = await fetch(`${BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail ?? 'Authentication failed')
        return
      }
      setToken(data.access_token)
      navigate('/')
    } catch {
      setError('Cannot reach server')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', padding: '32px', width: '100%', maxWidth: '360px' }}>
        <div style={{ marginBottom: '24px' }}>
          <div style={{ color: 'var(--accent)', fontSize: 'var(--fs-lg)', fontWeight: 700, letterSpacing: '3px' }}>FORGE</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', marginTop: '4px' }}>
            {mode === 'login' ? 'sign in to your account' : 'create an account'}
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>EMAIL</div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', padding: '6px 10px', outline: 'none', boxSizing: 'border-box' }}
              onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
              onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
            />
          </div>
          <div>
            <div style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', marginBottom: '4px' }}>PASSWORD</div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', padding: '6px 10px', outline: 'none', boxSizing: 'border-box' }}
              onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
              onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
            />
          </div>

          {error && (
            <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-sm)' }}>{error}</div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{ width: '100%', padding: '8px 0', background: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '1px', opacity: loading ? 0.5 : 1 }}
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
