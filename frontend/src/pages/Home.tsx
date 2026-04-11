import { useEffect } from 'react'
import { useEngagementStore } from '../store/engagement'
import { engagementsApi } from '../api/engagements'
import { EngagementDashboard } from '../components/EngagementDashboard'

export function Home() {
  const setEngagements = useEngagementStore((s) => s.setEngagements)

  useEffect(() => {
    engagementsApi.list().then(setEngagements).catch(console.error)
  }, [setEngagements])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 px-6 py-4">
        <h1 className="text-2xl font-bold text-orange-400">FORGE</h1>
        <p className="text-sm text-gray-400">Framework for Offensive Reasoning, Generation and Exploitation</p>
      </header>
      <main className="px-6 py-8">
        <EngagementDashboard />
      </main>
    </div>
  )
}
