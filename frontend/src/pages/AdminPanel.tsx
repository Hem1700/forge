import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminApi, type AuthUser } from '../api/auth'

const ROLES = ['viewer', 'analyst', 'admin', 'super_admin'] as const
type Role = typeof ROLES[number]

const ROLE_COLOR: Record<Role, string> = {
  viewer:      'var(--text-secondary)',
  analyst:     'var(--accent)',
  admin:       'var(--gate)',
  super_admin: 'var(--crit)',
}

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
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      <div style={{ borderBottom: '1px solid var(--border)', padding: '12px 24px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Link to="/" style={{ color: 'var(--accent)', fontWeight: 700, fontSize: 'var(--fs-lg)', letterSpacing: '3px', textDecoration: 'none' }}>FORGE</Link>
        <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-sm)' }}>/</span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', letterSpacing: '1px' }}>SUPER_ADMIN</span>
      </div>

      <div style={{ maxWidth: '900px', margin: '0 auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Provision user */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div style={{ borderBottom: '1px solid var(--border)', padding: '10px 16px', color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>PROVISION_USER</div>
          <div style={{ padding: '16px' }}>
            <form onSubmit={handleProvision} style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              <input
                value={provisionEmail}
                onChange={(e) => setProvisionEmail(e.target.value)}
                placeholder="email@example.com"
                type="email"
                required
                style={{ flex: '1 1 200px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', padding: '5px 10px', outline: 'none' }}
                onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
              />
              <input
                value={provisionPassword}
                onChange={(e) => setProvisionPassword(e.target.value)}
                placeholder="initial password"
                type="password"
                required
                style={{ flex: '1 1 160px', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontSize: 'var(--fs-md)', padding: '5px 10px', outline: 'none' }}
                onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)' }}
              />
              <select
                value={provisionRole}
                onChange={(e) => setProvisionRole(e.target.value)}
                style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: ROLE_COLOR[provisionRole as Role] ?? 'var(--text-primary)', fontSize: 'var(--fs-sm)', padding: '5px 10px', letterSpacing: '1px' }}
              >
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <button
                type="submit"
                disabled={provisioning}
                style={{ background: 'var(--accent-bg)', border: '1px solid var(--accent-dim)', color: 'var(--accent)', fontSize: 'var(--fs-sm)', padding: '5px 16px', letterSpacing: '1px', opacity: provisioning ? 0.5 : 1 }}
              >
                {provisioning ? '...' : '▶ provision'}
              </button>
            </form>
            {error && <div style={{ color: 'var(--crit)', fontSize: 'var(--fs-sm)', marginTop: '8px' }}>{error}</div>}
          </div>
        </div>

        {/* All users */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div style={{ borderBottom: '1px solid var(--border)', padding: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-label)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>ALL_USERS ({users.length})</span>
            <button
              onClick={load}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)' }}
            >
              refresh
            </button>
          </div>

          {loading && <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', padding: '16px' }}>loading…</div>}

          <div>
            {users.map((u) => (
              <div
                key={u.id}
                style={{ borderBottom: '1px solid var(--border-deep)', padding: '8px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-md)' }}>{u.email}</span>
                  {!u.is_active && (
                    <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-xs)', letterSpacing: '1px' }}>(inactive)</span>
                  )}
                </div>
                <select
                  value={u.role}
                  onChange={(e) => handleRoleChange(u.id, e.target.value)}
                  style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: ROLE_COLOR[u.role as Role] ?? 'var(--text-primary)', fontSize: 'var(--fs-xs)', padding: '3px 8px', letterSpacing: '1px' }}
                >
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
