import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

interface AttackPathDiagramProps {
  source: string
}

let initialized = false

export function AttackPathDiagram({ source }: AttackPathDiagramProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!initialized) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        themeVariables: {
          background: '#111827',
          primaryColor: '#f97316',
          primaryTextColor: '#f3f4f6',
          lineColor: '#6b7280',
          edgeLabelBackground: '#1f2937',
        },
      })
      initialized = true
    }

    if (!source || !ref.current) return
    setError(null)
    setReady(false)

    const renderId = `ap-${Math.random().toString(36).slice(2, 9)}`

    mermaid
      .render(renderId, source)
      .then(({ svg }) => {
        if (ref.current) {
          ref.current.innerHTML = svg
          setReady(true)
        }
      })
      .catch(() => {
        setError('Unable to render attack path diagram.')
      })
  }, [source])

  if (error) {
    return (
      <div className="text-red-400 text-xs p-3 bg-gray-800 rounded">
        {error}
      </div>
    )
  }

  return (
    <div className="relative">
      {!ready && (
        <div className="h-24 bg-gray-800 rounded animate-pulse" />
      )}
      <div
        ref={ref}
        className="w-full overflow-x-auto [&_svg]:max-w-full [&_svg]:h-auto"
      />
    </div>
  )
}
