import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/auth'
import { authApi } from '../api/auth'

interface Props {
  children: React.ReactNode
  requireRole?: 'viewer' | 'analyst' | 'admin' | 'super_admin'
}

export function ProtectedRoute({ children, requireRole = 'viewer' }: Props) {
  const { token, user, setUser, logout, isAtLeast } = useAuthStore()
  const [loading, setLoading] = useState(!user && !!token)

  useEffect(() => {
    if (!user && token) {
      authApi
        .me()
        .then(setUser)
        .catch(() => logout())
        .finally(() => setLoading(false))
    }
  }, [token, user, setUser, logout])

  if (!token) return <Navigate to="/login" replace />
  if (loading) return <div className="min-h-screen bg-neutral-950" />
  if (!isAtLeast(requireRole)) return <Navigate to="/" replace />
  return <>{children}</>
}
