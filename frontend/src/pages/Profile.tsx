import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/auth'
import { authApi, type ApiKey, type ApiKeyWithSecret } from '../api/auth'
import { NavBar } from '../components/NavBar'

const ROLE_COLOR: Record<string, string> = {
  viewer:      'var(--text-secondary)',
  analyst:     'var(--accent)',
  admin:       'var(--gate)',
  super_admin: 'var(--crit)',
}

export function Profile() {
  const { user, setUser } = useAuthStore()
  const [keys, setKeys] = useState<ApiKey[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [createdKey, setCreatedKey] = useState<ApiKeyWithSecret | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    authApi.me().then(setUser).catch(() => {})
    authApi.listApiKeys().then(setKeys).catch(() => {})
  }, [setUser])

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newKeyName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const key = await authApi.createApiKey(newKeyName.trim())
      setCreatedKey(key)
      setKeys((prev) => [key, ...prev])
      setNewKeyName('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create key')
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (id: string) => {
    await authApi.deleteApiKey(id)
    setKeys((prev) => prev.filter((k) => k.id !== id))
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      <NavBar />

      <div style={{ maxWidth: '680px', margin: '0 auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Profile info */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div style={{ borderBottom: '1px solid var(--border)', padding: '10px 16px', color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>PROFILE</div>
          {user && (
            <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>EMAIL</span>
                <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-md)' }}>{user.email}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>ROLE</span>
                <span style={{ color: ROLE_COLOR[user.role] ?? 'var(--text-primary)', fontSize: 'var(--fs-sm)', letterSpacing: '1px' }}>{user.role}</span>
              </div>
            </div>
          )}
        </div>

        {/* API Keys */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div style={{ borderBottom: '1px solid var(--border)', padding: '10px 16px', color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>API_KEYS</div>
          <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>
              use with{' '}
              <code style={{ color: 'var(--accent)' }}>forge configure --key &lt;key&gt;</code>
              {' '}or{' '}
              <code style={{ color: 'var(--accent)' }}>Authorization: Bearer &lt;key&gt;</code>
            </div>

            {createdKey && (
              <div style={{ background: 'var(--bg)', border: '1px solid var(--complete)', padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ color: 'var(--complete)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>KEY CREATED — COPY NOW, WON'T BE SHOWN AGAIN</div>
                <code style={{ color: 'var(--complete)', fontSize: 'var(--fs-sm)', wordBreak: 'break-all' }}>{createdKey.key}</code>
                <button
                  onClick={() => setCreatedKey(null)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', padding: 0, textAlign: 'left' }}
                >
                  dismiss
                </button>
              </div>
            )}

            <form onSubmit={handleCreateKey} style={{ display: 'flex', gap: '8px' }}>
              <input
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="key name (e.g. my-laptop)"
                style={{ flex: 1, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', padding: '5px 8px', outline: 'none' }}
                onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
              />
              <button
                type="submit"
                disabled={creating || !newKeyName.trim()}
                style={{ background: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: 'var(--fs-sm)', padding: '5px 16px', letterSpacing: '1px', opacity: (creating || !newKeyName.trim()) ? 0.5 : 1 }}
              >
                {creating ? '...' : 'create'}
              </button>
            </form>

            {error && <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-sm)' }}>{error}</div>}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {keys.length === 0 && (
                <div style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-sm)' }}>&gt; no api keys yet_</div>
              )}
              {keys.map((key) => (
                <div
                  key={key.id}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg)', border: '1px solid var(--border-deep)', padding: '6px 10px' }}
                >
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-md)' }}>{key.name}</span>
                    <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>{key.prefix}…</span>
                    {key.last_used_at && (
                      <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-sm)' }}>
                        last used {new Date(key.last_used_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => handleRevoke(key.id)}
                    style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--crit)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)' }}
                  >
                    revoke
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
