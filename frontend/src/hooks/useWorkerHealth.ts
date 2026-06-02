import { useEffect, useState } from 'react'
import { healthApi, type WorkerHealth } from '../api/health'

const POLL_MS = 30_000

export function useWorkerHealth(): WorkerHealth {
  const [health, setHealth] = useState<WorkerHealth>({ status: 'unknown', stats: null })

  useEffect(() => {
    let cancelled = false

    async function tick() {
      try {
        const next = await healthApi.worker()
        if (!cancelled) setHealth(next)
      } catch {
        if (!cancelled) setHealth({ status: 'unknown', stats: null })
      }
    }

    tick()
    const id = window.setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  return health
}
