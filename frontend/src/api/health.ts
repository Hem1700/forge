import { apiFetch } from './client'

export type WorkerStatus = 'up' | 'down' | 'unknown'

export interface WorkerHealth {
  status: WorkerStatus
  stats: string | null
}

export const healthApi = {
  worker: () => apiFetch<WorkerHealth>('/api/v1/health/worker'),
}
