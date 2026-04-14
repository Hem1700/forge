// frontend/src/components/PoCScript.tsx
import { useState } from 'react'
import type { PoCDetail } from '../types'

interface PoCScriptProps {
  poc: PoCDetail
}

const LANGUAGE_COLORS: Record<string, string> = {
  python: 'bg-blue-900/50 text-blue-300 border-blue-700',
  bash: 'bg-green-900/50 text-green-300 border-green-700',
}

export function PoCScript({ poc }: PoCScriptProps) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(poc.script)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopyError(true)
      setTimeout(() => setCopyError(false), 2000)
    }
  }

  function handleDownload() {
    const blob = new Blob([poc.script], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = poc.filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const langColor = LANGUAGE_COLORS[poc.language] ?? 'bg-gray-800 text-gray-300 border-gray-600'

  return (
    <div className="space-y-3">
      {/* Header: language badge + filename + buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded border font-mono ${langColor}`}>
          {poc.language}
        </span>
        <span className="text-xs text-gray-400 font-mono">{poc.filename}</span>
        <div className="ml-auto flex gap-2">
          <button
            onClick={handleCopy}
            className="text-xs text-gray-400 hover:text-gray-100 bg-gray-800 hover:bg-gray-700 px-3 py-1 rounded transition-colors"
          >
            {copyError ? 'Copy failed' : copied ? 'Copied!' : 'Copy'}
          </button>
          <button
            onClick={handleDownload}
            className="text-xs text-orange-400 hover:text-orange-300 bg-orange-900/20 hover:bg-orange-900/40 border border-orange-800 px-3 py-1 rounded transition-colors"
          >
            Download
          </button>
        </div>
      </div>

      {/* Script */}
      <pre className="text-xs font-mono text-green-300 bg-gray-800/80 border border-gray-700 p-4 rounded overflow-x-auto whitespace-pre max-h-80">
        {poc.script}
      </pre>

      {/* Setup */}
      {(poc.setup ?? []).length > 0 && (
        <div className="text-xs text-gray-400">
          <span className="text-gray-500">Setup: </span>
          {poc.setup.map((cmd, i) => (
            <code key={i} className="font-mono bg-gray-800 px-1.5 py-0.5 rounded text-gray-300 mr-1">
              {cmd}
            </code>
          ))}
        </div>
      )}

      {/* Notes */}
      {poc.notes && (
        <p className="text-xs text-gray-500 italic">{poc.notes}</p>
      )}
    </div>
  )
}
