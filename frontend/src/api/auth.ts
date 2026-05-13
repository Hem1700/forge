import { apiFetch } from './client'

export interface AuthUser {
  id: string
  email: string
  role: 'viewer' | 'analyst' | 'admin' | 'super_admin'
  is_active: boolean
  created_at: string
}

export interface ApiKey {
  id: string
  name: string
  prefix: string
  is_active: boolean
  created_at: string
  last_used_at: string | null
}

export interface ApiKeyWithSecret extends ApiKey {
  key: string
}

export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; token_type: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string) =>
    apiFetch<{ access_token: string; token_type: string }>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => apiFetch<AuthUser>('/api/v1/auth/me'),

  listApiKeys: () => apiFetch<ApiKey[]>('/api/v1/api-keys/'),

  createApiKey: (name: string) =>
    apiFetch<ApiKeyWithSecret>('/api/v1/api-keys/', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  deleteApiKey: (id: string) =>
    apiFetch<void>(`/api/v1/api-keys/${id}`, { method: 'DELETE' }),
}

export const adminApi = {
  listOrgUsers: () => apiFetch<AuthUser[]>('/api/v1/org/users'),
  updateUserRole: (userId: string, role: string) =>
    apiFetch<AuthUser>(`/api/v1/org/users/${userId}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    }),
  deleteUser: (userId: string) =>
    apiFetch<void>(`/api/v1/org/users/${userId}`, { method: 'DELETE' }),
  listAllUsers: () => apiFetch<AuthUser[]>('/api/v1/admin/users'),
  setUserRole: (userId: string, role: string) =>
    apiFetch<AuthUser>(`/api/v1/admin/users/${userId}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    }),
  provision: (email: string, password: string, role: string) =>
    apiFetch<AuthUser>('/api/v1/admin/provision', {
      method: 'POST',
      body: JSON.stringify({ email, password, role }),
    }),
}
