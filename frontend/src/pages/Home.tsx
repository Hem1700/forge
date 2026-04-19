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
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <EngagementDashboard />
    </div>
  )
}
