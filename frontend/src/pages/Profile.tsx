import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { authApi, type ApiKey, type ApiKeyWithSecret } from '../api/auth'

export function Profile() {
  const { user, setUser, logout } = useAuthStore()
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

  const ROLE_BADGE: Record<string, string> = {
    viewer: 'bg-neutral-700 text-neutral-300',
    analyst: 'bg-blue-900 text-blue-300',
    admin: 'bg-amber-900 text-amber-300',
    super_admin: 'bg-red-900 text-red-300',
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-4 flex items-center justify-between">
        <Link to="/" className="font-mono font-bold text-red-500 text-lg">FORGE</Link>
        <button onClick={logout} className="text-neutral-400 hover:text-neutral-200 text-sm font-mono">
          Sign out
        </button>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-8 space-y-8">
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 space-y-3">
          <h2 className="font-mono font-bold text-neutral-200">Profile</h2>
          {user && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-neutral-400 text-sm font-mono">Email</span>
                <span className="text-neutral-200 text-sm font-mono">{user.email}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-neutral-400 text-sm font-mono">Role</span>
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${ROLE_BADGE[user.role] ?? ''}`}>
                  {user.role}
                </span>
              </div>
            </div>
          )}
        </section>

        <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 space-y-4">
          <h2 className="font-mono font-bold text-neutral-200">API Keys</h2>
          <p className="text-neutral-500 text-sm font-mono">
            Use with <code className="text-red-400">forge configure --key &lt;key&gt;</code> or{' '}
            <code className="text-red-400">Authorization: Bearer &lt;key&gt;</code>
          </p>

          {createdKey && (
            <div className="bg-neutral-800 border border-green-800 rounded p-4 space-y-2">
              <p className="text-green-400 text-xs font-mono font-bold uppercase tracking-wider">
                Key created — copy it now, it won't be shown again
              </p>
              <code className="block text-green-300 text-sm break-all">{createdKey.key}</code>
              <button
                onClick={() => setCreatedKey(null)}
                className="text-neutral-500 hover:text-neutral-300 text-xs font-mono"
              >
                Dismiss
              </button>
            </div>
          )}

          <form onSubmit={handleCreateKey} className="flex gap-2">
            <input
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="Key name (e.g. my-laptop)"
              className="flex-1 bg-neutral-800 border border-neutral-700 rounded px-3 py-2 text-sm font-mono text-neutral-100 focus:outline-none focus:border-neutral-500"
            />
            <button
              type="submit"
              disabled={creating || !newKeyName.trim()}
              className="bg-red-700 hover:bg-red-600 text-white text-sm font-mono px-4 py-2 rounded disabled:opacity-50"
            >
              {creating ? '…' : 'Create'}
            </button>
          </form>
          {error && <p className="text-red-400 text-sm font-mono">{error}</p>}

          <div className="space-y-2">
            {keys.length === 0 && (
              <p className="text-neutral-600 text-sm font-mono">No API keys yet.</p>
            )}
            {keys.map((key) => (
              <div
                key={key.id}
                className="flex items-center justify-between bg-neutral-800 rounded px-3 py-2"
              >
                <div>
                  <span className="text-neutral-200 text-sm font-mono">{key.name}</span>
                  <span className="text-neutral-500 text-xs font-mono ml-3">{key.prefix}…</span>
                  {key.last_used_at && (
                    <span className="text-neutral-600 text-xs font-mono ml-3">
                      last used {new Date(key.last_used_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => handleRevoke(key.id)}
                  className="text-neutral-500 hover:text-red-400 text-xs font-mono"
                >
                  Revoke
                </button>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}
