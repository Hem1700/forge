import { useEffect, useRef, type ReactNode } from 'react'
import { useEngagementStore } from '../store/engagement'
import type { Severity, SwarmEvent } from '../types'

const SEV_COLOR: Record<Severity, string> = {
  critical: 'var(--crit)',
  high:     'var(--high)',
  medium:   'var(--medium)',
  low:      'var(--low)',
  info:     'var(--info)',
}

const K = { color: 'var(--text-label)' } as const
const V = { color: 'var(--accent-glow)' } as const

interface Rendered { tag: string; tagColor: string; msg: ReactNode }

function renderEvent(e: SwarmEvent): Rendered {
  const p = e.payload as Record<string, unknown>
  switch (e.type) {
    case 'agent_started': {
      const phase = (p.phase ?? p.agent_id ?? 'agent') as string
      const target = (p.target ?? p.path ?? p.hypothesis ?? '') as string
      return {
        tag: 'AGENT', tagColor: 'var(--accent)',
        msg: (
          <>
            <span style={K}>{phase}</span> <span style={V}>spawned</span>
            {target && <> → <span style={V}>{target}</span></>}
          </>
        ),
      }
    }
    case 'agent_completed': {
      const phase = (p.phase ?? p.agent_id ?? 'agent') as string
      const rest = Object.entries(p)
        .filter(([k]) => k !== 'phase' && k !== 'agent_id')
        .slice(0, 3)
        .map(([k, v]) => `${k}=${String(v)}`)
        .join(' · ')
      return {
        tag: 'DONE', tagColor: 'var(--complete)',
        msg: (
          <>
            <span style={K}>{phase}</span>
            {rest && <> <span style={V}>{rest}</span></>}
          </>
        ),
      }
    }
    case 'agent_thought': {
      const phase = (p.phase ?? 'thought') as string
      const tool = (p.tool as string | undefined) ?? ''
      const text = (p.text as string | undefined) ?? ''
      const args = (p.args as string | undefined) ?? ''
      const conf = p.confidence as number | undefined
      const result = (p.result as string | undefined) ?? ''
      if (phase === 'action') {
        return {
          tag: 'ACT', tagColor: 'var(--high)',
          msg: (
            <>
              <span style={K}>{tool}</span>
              {args && <> <span style={V}>{args}</span></>}
            </>
          ),
        }
      }
      if (phase === 'observation') {
        return {
          tag: 'OBS', tagColor: 'var(--text-secondary)',
          msg: (
            <>
              <span style={K}>{tool}</span>
              {result && <> → <span style={{ color: 'var(--text-primary)' }}>{result}</span></>}
            </>
          ),
        }
      }
      if (phase === 'conclusion') {
        return {
          tag: 'CONCL', tagColor: 'var(--complete)',
          msg: (
            <>
              {text}
              {conf != null && <> · <span style={K}>conf {Math.round(conf * 100)}%</span></>}
            </>
          ),
        }
      }
      // thought (default)
      return {
        tag: 'THINK', tagColor: 'var(--accent)',
        msg: (
          <>
            {text}
            {tool && <> · <span style={K}>→ {tool}</span></>}
            {conf != null && <> · <span style={K}>conf {Math.round(conf * 100)}%</span></>}
          </>
        ),
      }
    }
    case 'finding_judged': {
      const j = (p.judgment ?? {}) as Record<string, unknown>
      const fp = j.likely_false_positive as boolean | undefined
      const reasoning = (j.reasoning as string | undefined) ?? ''
      return {
        tag: 'JUDGE',
        tagColor: fp ? 'var(--text-secondary)' : 'var(--complete)',
        msg: (
          <>
            <span style={K}>{fp ? 'likely FP' : 'real'}</span>
            {reasoning && <> · <span style={{ color: 'var(--text-secondary)' }}>{reasoning}</span></>}
          </>
        ),
      }
    }
    case 'finding_discovered': {
      const f = (p.finding ?? {}) as Record<string, unknown>
      const sev = ((f.severity as string | undefined) ?? 'info') as Severity
      const desc = (f.description as string | undefined)?.slice(0, 80)
      const vuln = (f.vulnerability_class ?? f.attack_class ?? f.title ?? f.vulnerability ?? desc ?? 'finding') as string
      const loc = (f.affected_surface ?? f.endpoint ?? f.file ?? (f.package ? `pkg:${f.package}` : '')) as string
      const conf = f.confidence_score as number | undefined
      return {
        tag: 'FIND', tagColor: 'var(--high)',
        msg: (
          <>
            <span style={{ color: SEV_COLOR[sev] }}>[{sev.toUpperCase().slice(0, 4)}]</span>{' '}
            {vuln}
            {loc && <> · <span style={V}>{loc}</span></>}
            {conf != null && <> · conf <span style={K}>{Math.round(conf * 100)}%</span></>}
          </>
        ),
      }
    }
    case 'gate_triggered': {
      const gate = (p.gate_status ?? (p.engagement as Record<string, unknown> | undefined)?.gate_status ?? '') as string
      return {
        tag: 'GATE', tagColor: 'var(--gate)',
        msg: (
          <>
            human approval required{gate && <> · <span style={V}>{gate}</span></>}
          </>
        ),
      }
    }
    case 'campaign_complete': {
      const status = (p.status ?? 'complete') as string
      const err = p.error as string | undefined
      return {
        tag: 'END',
        tagColor: status === 'error' ? 'var(--aborted)' : 'var(--complete)',
        msg: (
          <>
            campaign {status}
            {err && <> · <span style={{ color: 'var(--crit)' }}>{err}</span></>}
          </>
        ),
      }
    }
    case 'progress': {
      const phase = (p.phase ?? '') as string
      const detail = (p.detail ?? '') as string
      return {
        tag: 'PROG', tagColor: 'var(--accent-glow)',
        msg: (
          <>
            <span style={K}>{phase}</span>
            {detail && <> <span>{detail}</span></>}
          </>
        ),
      }
    }
    case 'ping':
    default:
      return {
        tag: 'PING', tagColor: 'var(--text-secondary)',
        msg: <span style={{ color: 'var(--text-dim)' }}>ping</span>,
      }
  }
}

const COLS = '78px 68px 1fr'

export function SwarmMonitor() {
  const events = useEngagementStore((s) => s.events)
  const agents = useEngagementStore((s) => s.agents)
  const activeEngagement = useEngagementStore((s) => s.activeEngagement)
  const bodyRef = useRef<HTMLDivElement>(null)

  const streaming = activeEngagement?.status === 'running'
  const ordered = [...events].reverse().slice(-80)

  useEffect(() => {
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [ordered.length])

  return (
    <div style={{ border: '1px solid var(--border)', borderLeft: '2px solid var(--accent)', background: 'var(--surface)' }}>
      {/* Panel header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', padding: '8px 14px' }}>
        <span style={{ color: 'var(--accent)', fontSize: 'var(--fs-sm)', letterSpacing: '2px' }}>▌ LIVE SWARM CONSOLE</span>
        <div style={{ display: 'flex', gap: '8px', fontSize: 'var(--fs-xs)', color: 'var(--text-label)' }}>
          <span style={{ border: '1px solid var(--border)', padding: '1px 6px' }}>{agents.length} AGENT{agents.length === 1 ? '' : 'S'}</span>
          <span style={{ border: '1px solid var(--border)', padding: '1px 6px' }}>{events.length} EVENT{events.length === 1 ? '' : 'S'}</span>
          <span style={{ border: '1px solid var(--border)', padding: '1px 6px', color: streaming ? 'var(--running)' : 'var(--text-secondary)' }}>
            {streaming ? '● STREAMING' : '○ IDLE'}
          </span>
        </div>
      </div>

      {/* Event log */}
      <div ref={bodyRef} style={{ height: '460px', overflowY: 'auto', padding: '10px 14px' }}>
        {ordered.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', padding: '16px 0' }}>
            &gt; waiting for events_
          </div>
        ) : (
          ordered.map((event, idx) => {
            const ts = new Date(event.timestamp).toLocaleTimeString('en-US', { hour12: false })
            const r = renderEvent(event)
            return (
              <div key={idx} style={{ display: 'grid', gridTemplateColumns: COLS, gap: '10px', padding: '4px 0', alignItems: 'baseline', borderBottom: '1px solid var(--border-deep)' }}>
                <span style={{ color: 'var(--text-dim)', fontSize: 'var(--fs-xs)' }}>{ts}</span>
                <span style={{ color: r.tagColor, fontSize: 'var(--fs-tiny)', letterSpacing: '2px' }}>{r.tag}</span>
                <span style={{ color: 'var(--text-primary)', fontSize: 'var(--fs-sm)', wordBreak: 'break-word' }}>{r.msg}</span>
              </div>
            )
          })
        )}
      </div>

      {/* Cursor footer */}
      <div style={{ borderTop: '1px solid var(--border)', padding: '6px 14px', color: 'var(--accent)', fontSize: 'var(--fs-sm)', display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span>▶</span>
        <span style={{ display: 'inline-block', width: '7px', height: '12px', background: 'var(--accent)', animation: 'forgeblink 1s steps(2) infinite' }} />
      </div>

      <style>{`@keyframes forgeblink { to { background: transparent; } }`}</style>
    </div>
  )
}
