import { Link, useLocation } from 'react-router-dom'
import { useAuthStore } from '../store/auth'

interface Props {
  right?: React.ReactNode
}

export function NavBar({ right }: Props) {
  const { user, logout } = useAuthStore()
  const { pathname } = useLocation()

  const isAdmin = user?.role === 'admin' || user?.role === 'super_admin'
  const isSuperAdmin = user?.role === 'super_admin'

  const navLink = (to: string, label: string) => {
    const active = pathname === to
    return (
      <Link
        to={to}
        style={{
          color: active ? 'var(--accent)' : 'var(--text-secondary)',
          fontSize: 'var(--fs-sm)',
          letterSpacing: '1px',
          textDecoration: 'none',
        }}
        onMouseEnter={(e) => { if (!active) (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-primary)' }}
        onMouseLeave={(e) => { if (!active) (e.currentTarget as HTMLAnchorElement).style.color = 'var(--text-secondary)' }}
      >
        {label}
      </Link>
    )
  }

  return (
    <div style={{ borderBottom: '1px solid var(--border)', padding: '10px 24px', display: 'flex', alignItems: 'center', gap: '20px' }}>
      <Link
        to="/"
        style={{ color: 'var(--accent)', fontWeight: 700, fontSize: 'var(--fs-lg)', letterSpacing: '3px', textDecoration: 'none', flexShrink: 0 }}
      >
        FORGE
      </Link>

      <span style={{ color: 'var(--border)', fontSize: 'var(--fs-sm)' }}>|</span>

      {navLink('/', 'home')}
      {navLink('/profile', 'profile')}
      {isAdmin && navLink('/org/settings', 'org')}
      {isSuperAdmin && navLink('/admin', 'super admin')}

      <div style={{ flex: 1 }} />

      {right}

      {user && (
        <button
          onClick={logout}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 'var(--fs-xs)', letterSpacing: '1px', padding: 0 }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--crit)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)' }}
        >
          sign out
        </button>
      )}
    </div>
  )
}
