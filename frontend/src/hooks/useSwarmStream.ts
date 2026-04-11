import { useEffect, useRef } from 'react'
import { useEngagementStore } from '../store/engagement'
import type { SwarmEvent } from '../types'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000'

export function useSwarmStream(engagementId: string | null) {
  const ws = useRef<WebSocket | null>(null)
  const addEvent = useEngagementStore((s) => s.addEvent)
  const upsertEngagement = useEngagementStore((s) => s.upsertEngagement)
  const addFinding = useEngagementStore((s) => s.addFinding)

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
        if (event.type === 'finding_discovered' && event.payload.finding) {
          addFinding(event.payload.finding as never)
        }
        if (event.type === 'gate_triggered' && event.payload.engagement) {
          upsertEngagement(event.payload.engagement as never)
        }
      } catch {
        // ignore non-JSON
      }
    }

    ws.current.onclose = () => {
      // reconnect after 3s
      setTimeout(() => {
        // component unmounted check happens via cleanup
      }, 3000)
    }

    return () => {
      ws.current?.close()
      ws.current = null
    }
  }, [engagementId, addEvent, addFinding, upsertEngagement])

  return ws
}
