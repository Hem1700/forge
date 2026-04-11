export type EngagementStatus = 'pending' | 'running' | 'paused_at_gate' | 'complete' | 'aborted'
export type GateStatus = 'gate_1' | 'gate_2' | 'gate_3' | 'complete'
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type TargetType = 'web' | 'local_codebase' | 'binary'

export interface Engagement {
  id: string
  target_url: string
  target_type: TargetType
  target_path: string | null
  status: EngagementStatus
  gate_status: GateStatus
  created_at: string
  completed_at: string | null
}

export interface Finding {
  id: string
  engagement_id: string
  title: string
  severity: Severity
  attack_class: string
  endpoint: string
  evidence: string
  validated: boolean
  confidence_score: number
  created_at: string
}

export interface AgentInfo {
  agent_id: string
  agent_type: string
  status: string
  engagement_id: string
}

export interface SwarmEvent {
  type: 'agent_started' | 'agent_completed' | 'finding_discovered' | 'gate_triggered' | 'campaign_complete' | 'ping'
  payload: Record<string, unknown>
  timestamp: string
}
