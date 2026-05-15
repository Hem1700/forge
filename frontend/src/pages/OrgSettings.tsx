import { useEffect, useState } from 'react'
import { adminApi, type AuthUser } from '../api/auth'
import { useAuthStore } from '../store/auth'
import { NavBar } from '../components/NavBar'

const ROLES = ['viewer', 'analyst', 'admin', 'super_admin'] as const
type Role = typeof ROLES[number]

const ROLE_COLOR: Record<Role, string> = {
  viewer:      'var(--text-secondary)',
  analyst:     'var(--accent)',
  admin:       'var(--gate)',
  super_admin: 'var(--crit)',
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

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      <NavBar />

      <div style={{ maxWidth: '760px', margin: '0 auto', padding: '24px' }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div style={{ borderBottom: '1px solid var(--border)', padding: '10px 16px', color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>USERS</div>

          {loading && <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', padding: '16px' }}>loading…</div>}
          {error && <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-sm)', padding: '16px' }}>{error}</div>}

          <div>
            {users.map((u) => (
              <div
                key={u.id}
                style={{ borderBottom: '1px solid var(--border-deep)', padding: '8px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-md)' }}>{u.email}</span>
                  {u.id === me?.id && (
                    <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>(you)</span>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <select
                    value={u.role}
                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                    disabled={u.id === me?.id}
                    style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: ROLE_COLOR[u.role as Role] ?? 'var(--text-primary)', fontSize: 'var(--fs-xs)', padding: '3px 8px', letterSpacing: '1px', opacity: u.id === me?.id ? 0.5 : 1 }}
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
                      style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', padding: 0 }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--crit)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)' }}
                    >
                      remove
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
