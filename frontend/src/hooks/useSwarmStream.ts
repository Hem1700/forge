import { useEffect, useRef } from 'react'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import type { SwarmEvent } from '../types'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000'

export function useSwarmStream(engagementId: string | null) {
  const ws = useRef<WebSocket | null>(null)
  const refetchTimer = useRef<number | null>(null)
  const addEvent = useEngagementStore((s) => s.addEvent)
  const upsertEngagement = useEngagementStore((s) => s.upsertEngagement)
  const setFindings = useEngagementStore((s) => s.setFindings)

  useEffect(() => {
    if (!engagementId) return

    ws.current = new WebSocket(`${WS_URL}/ws/${engagementId}`)

    ws.current.onmessage = (msg) => {
      if (msg.data === 'ping') {
        ws.current?.send('pong')
        return
      }
      try {
        const event: SwarmEvent = JSON.parse(msg.data)
        addEvent(event)
        if (event.type === 'finding_discovered') {
          // Raw agent payload lacks id/engagement_id; refetch the canonical list.
          if (refetchTimer.current) window.clearTimeout(refetchTimer.current)
          refetchTimer.current = window.setTimeout(() => {
            engagementsApi.findings(engagementId).then(setFindings).catch(() => {})
          }, 300)
        }
        if (event.type === 'gate_triggered' && event.payload.engagement) {
          upsertEngagement(event.payload.engagement as never)
        }
      } catch {
        // ignore non-JSON
      }
    }

    return () => {
      if (refetchTimer.current) window.clearTimeout(refetchTimer.current)
      ws.current?.close()
      ws.current = null
    }
  }, [engagementId, addEvent, setFindings, upsertEngagement])

  return ws
}
