import { apiFetch } from './client'
import type { FindingDetail, ExploitDetail, PoCDetail, ExploitScript, ExploitExecution } from '../types'

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

  generateExploitScript: (findingId: string) =>
    apiFetch<ExploitScript>(`/api/v1/findings/${findingId}/exploit/generate`, {
      method: 'POST',
    }),

  executeExploit: (findingId: string) =>
    apiFetch<ExploitExecution>(`/api/v1/findings/${findingId}/exploit/execute`, {
      method: 'POST',
      body: JSON.stringify({ confirmed: true }),
    }),

  overrideVerdict: (findingId: string, verdict: string) =>
    apiFetch<ExploitExecution>(`/api/v1/findings/${findingId}/exploit/execution`, {
      method: 'PATCH',
      body: JSON.stringify({ verdict }),
    }),
}
