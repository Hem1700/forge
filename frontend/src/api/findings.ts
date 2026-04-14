import { apiFetch } from './client'
import type { FindingDetail, ExploitDetail, PoCDetail } from '../types'

export const findingsApi = {
  get: (findingId: string) =>
    apiFetch<FindingDetail>(`/api/v1/findings/${findingId}`),

  generateExploit: (findingId: string) =>
    apiFetch<ExploitDetail>(`/api/v1/findings/${findingId}/exploit`, {
      method: 'POST',
    }),

  generatePoC: (findingId: string) =>
    apiFetch<PoCDetail>(`/api/v1/findings/${findingId}/poc`, {
      method: 'POST',
    }),
}
