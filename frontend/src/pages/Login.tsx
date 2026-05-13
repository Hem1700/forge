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
    <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
      <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-8 w-full max-w-sm space-y-6">
        <div>
          <h1 className="text-2xl font-mono font-bold text-red-500">FORGE</h1>
          <p className="text-neutral-500 text-sm mt-1">
            {mode === 'login' ? 'Sign in to your account' : 'Create an account'}
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-mono text-neutral-400 mb-1 uppercase tracking-wider">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-neutral-800 border border-neutral-700 rounded px-3 py-2 text-neutral-100 text-sm font-mono focus:outline-none focus:border-red-700"
              required
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-neutral-400 mb-1 uppercase tracking-wider">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-neutral-800 border border-neutral-700 rounded px-3 py-2 text-neutral-100 text-sm font-mono focus:outline-none focus:border-red-700"
              required
            />
          </div>
          {error && (
            <p className="text-red-400 text-sm font-mono">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-red-700 hover:bg-red-600 text-white font-mono text-sm py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
        <p className="text-neutral-500 text-sm text-center font-mono">
          {mode === 'login' ? (
            <>
              No account?{' '}
              <button
                onClick={() => { setMode('register'); setError(null) }}
                className="text-red-500 hover:text-red-400"
              >
                Register
              </button>
            </>
          ) : (
            <>
              Have an account?{' '}
              <button
                onClick={() => { setMode('login'); setError(null) }}
                className="text-red-500 hover:text-red-400"
              >
                Sign in
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
