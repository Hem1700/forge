import { useEffect, useRef } from 'react'
import { useEngagementStore } from '../store/engagement'
import { useAuthStore } from '../store/auth'
import { engagementsApi } from '../api/engagements'
import type { SwarmEvent } from '../types'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000'

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 1_000

// WS close codes the backend uses to signal terminal auth failure.
// Don't retry on these — the user needs to re-authenticate.
const TERMINAL_CODES = new Set([4400, 4401, 4403])

export function useSwarmStream(engagementId: string | null) {
  const ws = useRef<WebSocket | null>(null)
  const refetchTimer = useRef<number | null>(null)
  const reconnectTimer = useRef<number | null>(null)
  const attempts = useRef(0)
  const lastEventId = useRef<number | null>(null)
  const closedByEffect = useRef(false)

  const addEvent = useEngagementStore((s) => s.addEvent)
  const upsertEngagement = useEngagementStore((s) => s.upsertEngagement)
  const setActiveEngagement = useEngagementStore((s) => s.setActiveEngagement)
  const setFindings = useEngagementStore((s) => s.setFindings)
  const setStreamState = useEngagementStore((s) => s.setStreamState)
  const token = useAuthStore((s) => s.token)

  useEffect(() => {
    if (!engagementId || !token) return
    closedByEffect.current = false

    const connect = () => {
      attempts.current === 0
        ? setStreamState('connecting')
        : setStreamState('reconnecting')

      const params = new URLSearchParams({ token })
      if (lastEventId.current != null) {
        params.set('since', String(lastEventId.current))
      }
      const url = `${WS_URL}/ws/${engagementId}?${params.toString()}`
      const socket = new WebSocket(url)
      ws.current = socket

      socket.onopen = () => {
        attempts.current = 0
        setStreamState('live')
      }

      socket.onmessage = (msg) => {
        if (msg.data === 'ping') {
          socket.send('pong')
          return
        }
        try {
          const event: SwarmEvent = JSON.parse(msg.data)
          if (typeof event.id === 'number') {
            lastEventId.current = event.id
          }
          if (event.type === 'stream_error') {
            setStreamState('offline')
            return
          }
          addEvent(event)
          if (event.type === 'finding_discovered' || event.type === 'finding_judged') {
            if (refetchTimer.current) window.clearTimeout(refetchTimer.current)
            refetchTimer.current = window.setTimeout(() => {
              engagementsApi.findings(engagementId).then(setFindings).catch(() => {})
            }, 300)
          }
          if (event.type === 'gate_triggered' && event.payload.engagement) {
            upsertEngagement(event.payload.engagement as never)
          }
          if (event.type === 'campaign_complete') {
            engagementsApi.get(engagementId).then(setActiveEngagement).catch(() => {})
            engagementsApi.findings(engagementId).then(setFindings).catch(() => {})
          }
        } catch {
          // ignore non-JSON
        }
      }

      socket.onclose = (ev) => {
        if (closedByEffect.current) return
        if (TERMINAL_CODES.has(ev.code)) {
          setStreamState('offline')
          return
        }
        const delay = Math.min(BASE_BACKOFF_MS * 2 ** attempts.current, MAX_BACKOFF_MS)
        attempts.current += 1
        setStreamState('reconnecting')
        reconnectTimer.current = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closedByEffect.current = true
      if (refetchTimer.current) window.clearTimeout(refetchTimer.current)
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current)
      ws.current?.close()
      ws.current = null
      attempts.current = 0
      lastEventId.current = null
      setStreamState('idle')
    }
  }, [engagementId, token, addEvent, setFindings, setActiveEngagement, upsertEngagement, setStreamState])

  return ws
}
