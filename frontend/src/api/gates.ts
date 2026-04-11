import { apiFetch } from './client'
import type { Engagement } from '../types'

export const gatesApi = {
  decide: (engagementId: string, approved: boolean, notes?: string) =>
    apiFetch<Engagement>(`/api/v1/gates/${engagementId}/decide`, {
      method: 'POST',
      body: JSON.stringify({ approved, notes: notes ?? '' }),
    }),
}
