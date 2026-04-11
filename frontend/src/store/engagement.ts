import { create } from 'zustand'
import type { Engagement, Finding, AgentInfo, SwarmEvent } from '../types'

interface EngagementState {
  engagements: Engagement[]
  activeEngagement: Engagement | null
  findings: Finding[]
  agents: AgentInfo[]
  events: SwarmEvent[]
  setEngagements: (e: Engagement[]) => void
  setActiveEngagement: (e: Engagement | null) => void
  upsertEngagement: (e: Engagement) => void
  addFinding: (f: Finding) => void
  setFindings: (f: Finding[]) => void
  setAgents: (a: AgentInfo[]) => void
  addEvent: (e: SwarmEvent) => void
}

export const useEngagementStore = create<EngagementState>((set) => ({
  engagements: [],
  activeEngagement: null,
  findings: [],
  agents: [],
  events: [],
  setEngagements: (engagements) => set({ engagements }),
  setActiveEngagement: (activeEngagement) => set({ activeEngagement }),
  upsertEngagement: (engagement) =>
    set((s) => ({
      engagements: s.engagements.some((e) => e.id === engagement.id)
        ? s.engagements.map((e) => (e.id === engagement.id ? engagement : e))
        : [...s.engagements, engagement],
      activeEngagement: s.activeEngagement?.id === engagement.id ? engagement : s.activeEngagement,
    })),
  addFinding: (finding) => set((s) => ({ findings: [...s.findings, finding] })),
  setFindings: (findings) => set({ findings }),
  setAgents: (agents) => set({ agents }),
  addEvent: (event) => set((s) => ({ events: [event, ...s.events].slice(0, 100) })),
}))
