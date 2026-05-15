import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminApi, type AuthUser } from '../api/auth'
import { useAuthStore } from '../store/auth'

const ROLES = ['viewer', 'analyst', 'admin', 'super_admin'] as const
type Role = typeof ROLES[number]

const ROLE_BADGE: Record<Role, string> = {
  viewer: 'bg-neutral-700 text-neutral-300',
  analyst: 'bg-blue-900 text-blue-300',
  admin: 'bg-amber-900 text-amber-300',
  super_admin: 'bg-red-900 text-red-300',
}

export function OrgSettings() {
  const [users, setUsers] = useState<AuthUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { user: me } = useAuthStore()

  useEffect(() => {
    adminApi
      .listOrgUsers()
      .then(setUsers)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const handleRoleChange = async (userId: string, role: string) => {
    try {
      const updated = await adminApi.updateUserRole(userId, role)
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to update role')
    }
  }

  const handleDelete = async (userId: string) => {
    if (!confirm('Remove this user from the org?')) return
    try {
      await adminApi.deleteUser(userId)
      setUsers((prev) => prev.filter((u) => u.id !== userId))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to remove user')
    }
  }

  // Suppress unused variable warning — ROLE_BADGE is defined for potential future use
  void ROLE_BADGE

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-4 flex items-center gap-4">
        <Link to="/" className="font-mono font-bold text-red-500 text-lg">FORGE</Link>
        <span className="text-neutral-600 font-mono">/</span>
        <span className="text-neutral-400 font-mono text-sm">Org Settings</span>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        <div className="bg-neutral-900 border border-neutral-800 rounded-lg">
          <div className="px-6 py-4 border-b border-neutral-800">
            <h2 className="font-mono font-bold text-neutral-200">Users</h2>
          </div>

          {loading && <p className="text-neutral-500 font-mono text-sm px-6 py-4">Loading…</p>}
          {error && <p className="text-red-400 font-mono text-sm px-6 py-4">{error}</p>}

          <div className="divide-y divide-neutral-800">
            {users.map((u) => (
              <div key={u.id} className="px-6 py-3 flex items-center justify-between">
                <div className="space-y-0.5">
                  <span className="text-neutral-200 text-sm font-mono">{u.email}</span>
                  {u.id === me?.id && (
                    <span className="text-neutral-600 text-xs font-mono ml-2">(you)</span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <select
                    value={u.role}
                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                    disabled={u.id === me?.id}
                    className="bg-neutral-800 border border-neutral-700 rounded px-2 py-1 text-xs font-mono text-neutral-300 disabled:opacity-50"
                  >
                    {ROLES.filter((r) => {
                      if (r === 'super_admin' && me?.role !== 'super_admin') return false
                      return true
                    }).map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                  {u.id !== me?.id && (
                    <button
                      onClick={() => handleDelete(u.id)}
                      className="text-neutral-500 hover:text-red-400 text-xs font-mono"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
