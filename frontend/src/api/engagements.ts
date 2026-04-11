import { apiFetch } from './client'
import type { Engagement, Finding } from '../types'

export const engagementsApi = {
  list: () => apiFetch<Engagement[]>('/api/v1/engagements/'),
  get: (id: string) => apiFetch<Engagement>(`/api/v1/engagements/${id}`),
  create: (data: { target_url: string; target_type?: string; target_path?: string; target_scope?: string[]; target_out_of_scope?: string[] }) =>
    apiFetch<Engagement>('/api/v1/engagements/', { method: 'POST', body: JSON.stringify(data) }),
  start: (id: string) =>
    apiFetch<{ status: string; engagement_id: string }>(`/api/v1/engagements/${id}/start`, { method: 'POST' }),
  updateStatus: (id: string, status: string) =>
    apiFetch<Engagement>(`/api/v1/engagements/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  delete: (id: string) =>
    apiFetch<void>(`/api/v1/engagements/${id}`, { method: 'DELETE' }),
  findings: (id: string) =>
    apiFetch<Finding[]>(`/api/v1/engagements/${id}/findings`),
}
