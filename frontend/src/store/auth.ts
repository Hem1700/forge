import { create } from 'zustand'

interface AuthUser {
  id: string
  email: string
  role: 'viewer' | 'analyst' | 'admin' | 'super_admin'
  is_active: boolean
  created_at: string
}

interface AuthState {
  token: string | null
  user: AuthUser | null
  setToken: (token: string) => void
  setUser: (user: AuthUser) => void
  logout: () => void
  isAtLeast: (role: AuthUser['role']) => boolean
}

const ROLE_RANK: Record<AuthUser['role'], number> = {
  viewer: 0,
  analyst: 1,
  admin: 2,
  super_admin: 3,
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('forge_token'),
  user: null,
  setToken: (token) => {
    localStorage.setItem('forge_token', token)
    set({ token })
  },
  setUser: (user) => set({ user }),
  logout: () => {
    localStorage.removeItem('forge_token')
    set({ token: null, user: null })
  },
  isAtLeast: (role) => {
    const u = get().user
    if (!u) return false
    return ROLE_RANK[u.role] >= ROLE_RANK[role]
  },
}))
