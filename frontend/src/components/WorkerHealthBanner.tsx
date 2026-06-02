import { useLocation } from 'react-router-dom'
import { useWorkerHealth } from '../hooks/useWorkerHealth'

export function WorkerHealthBanner() {
  const { pathname } = useLocation()
  const { status, stats } = useWorkerHealth()

  // Don't render on print routes — would bleed into PDF exports.
  if (pathname.startsWith('/print/')) return null
  if (status === 'up') return null

  const isDown = status === 'down'
  const color = isDown ? 'var(--aborted)' : 'var(--gate)'
  const label = isDown ? '✕ WORKER OFFLINE' : '⚠ WORKER STATUS UNKNOWN'
  const detail = isDown
    ? 'No Arq worker has reported in. Engagements you launch will queue but never execute. Start the worker (make worker).'
    : 'Cannot reach Redis to check worker liveness. Pipelines may or may not be running.'

  return (
    <div
      style={{
        background: 'black',
        borderBottom: `1px solid ${color}`,
        color,
        fontFamily: 'monospace',
        fontSize: '12px',
        padding: '8px 16px',
        display: 'flex',
        gap: '16px',
        alignItems: 'baseline',
      }}
      role="alert"
    >
      <strong>{label}</strong>
      <span style={{ color: 'var(--text-dim, #888)' }}>{detail}</span>
      {stats && <span style={{ marginLeft: 'auto', opacity: 0.6 }}>{stats}</span>}
    </div>
  )
}
