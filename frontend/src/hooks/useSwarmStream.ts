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
  const setActiveEngagement = useEngagementStore((s) => s.setActiveEngagement)
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
        if (event.type === 'finding_discovered' || event.type === 'finding_judged') {
          // Refetch the canonical list so judge verdicts and full finding shape
          // arrive together. Debounced because both event types burst.
          if (refetchTimer.current) window.clearTimeout(refetchTimer.current)
          refetchTimer.current = window.setTimeout(() => {
            engagementsApi.findings(engagementId).then(setFindings).catch(() => {})
          }, 300)
        }
        if (event.type === 'gate_triggered' && event.payload.engagement) {
          upsertEngagement(event.payload.engagement as never)
        }
        if (event.type === 'campaign_complete') {
          // Pipeline finished — refetch canonical state so the header flips
          // to complete/aborted and we catch any findings saved after the last
          // finding_discovered event.
          engagementsApi.get(engagementId).then(setActiveEngagement).catch(() => {})
          engagementsApi.findings(engagementId).then(setFindings).catch(() => {})
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
  }, [engagementId, addEvent, setFindings, setActiveEngagement, upsertEngagement])

  return ws
}
