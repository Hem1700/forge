import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminApi, AuthUser } from '../api/auth'

const ROLES = ['viewer', 'analyst', 'admin', 'super_admin'] as const

export function AdminPanel() {
  const [users, setUsers] = useState<AuthUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [provisionEmail, setProvisionEmail] = useState('')
  const [provisionPassword, setProvisionPassword] = useState('')
  const [provisionRole, setProvisionRole] = useState<string>('viewer')
  const [provisioning, setProvisioning] = useState(false)

  const load = () => {
    setLoading(true)
    adminApi
      .listAllUsers()
      .then(setUsers)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleRoleChange = async (userId: string, role: string) => {
    try {
      const updated = await adminApi.setUserRole(userId, role)
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to update role')
    }
  }

  const handleProvision = async (e: React.FormEvent) => {
    e.preventDefault()
    setProvisioning(true)
    setError(null)
    try {
      const newUser = await adminApi.provision(provisionEmail, provisionPassword, provisionRole)
      setUsers((prev) => [newUser, ...prev])
      setProvisionEmail('')
      setProvisionPassword('')
      setProvisionRole('viewer')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to provision user')
    } finally {
      setProvisioning(false)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-4 flex items-center gap-4">
        <Link to="/" className="font-mono font-bold text-red-500 text-lg">FORGE</Link>
        <span className="text-neutral-600 font-mono">/</span>
        <span className="text-neutral-400 font-mono text-sm">Super Admin</span>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-8">
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 space-y-4">
          <h2 className="font-mono font-bold text-neutral-200">Provision User</h2>
          <form onSubmit={handleProvision} className="flex flex-wrap gap-2">
            <input
              value={provisionEmail}
              onChange={(e) => setProvisionEmail(e.target.value)}
              placeholder="email@example.com"
              type="email"
              required
              className="flex-1 min-w-48 bg-neutral-800 border border-neutral-700 rounded px-3 py-2 text-sm font-mono text-neutral-100 focus:outline-none focus:border-neutral-500"
            />
            <input
              value={provisionPassword}
              onChange={(e) => setProvisionPassword(e.target.value)}
              placeholder="Initial password"
              type="password"
              required
              className="flex-1 min-w-40 bg-neutral-800 border border-neutral-700 rounded px-3 py-2 text-sm font-mono text-neutral-100 focus:outline-none focus:border-neutral-500"
            />
            <select
              value={provisionRole}
              onChange={(e) => setProvisionRole(e.target.value)}
              className="bg-neutral-800 border border-neutral-700 rounded px-3 py-2 text-sm font-mono text-neutral-300"
            >
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button
              type="submit"
              disabled={provisioning}
              className="bg-red-700 hover:bg-red-600 text-white text-sm font-mono px-4 py-2 rounded disabled:opacity-50"
            >
              {provisioning ? '…' : 'Provision'}
            </button>
          </form>
          {error && <p className="text-red-400 text-sm font-mono">{error}</p>}
        </section>

        <section className="bg-neutral-900 border border-neutral-800 rounded-lg">
          <div className="px-6 py-4 border-b border-neutral-800 flex items-center justify-between">
            <h2 className="font-mono font-bold text-neutral-200">All Users ({users.length})</h2>
            <button onClick={load} className="text-neutral-500 hover:text-neutral-300 text-xs font-mono">
              Refresh
            </button>
          </div>

          {loading && <p className="text-neutral-500 font-mono text-sm px-6 py-4">Loading…</p>}

          <div className="divide-y divide-neutral-800">
            {users.map((u) => (
              <div key={u.id} className="px-6 py-3 flex items-center justify-between">
                <div>
                  <span className="text-neutral-200 text-sm font-mono">{u.email}</span>
                  {!u.is_active && (
                    <span className="text-neutral-600 text-xs font-mono ml-2">(inactive)</span>
                  )}
                </div>
                <select
                  value={u.role}
                  onChange={(e) => handleRoleChange(u.id, e.target.value)}
                  className="bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-300"
                >
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}
