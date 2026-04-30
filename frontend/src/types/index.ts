export type EngagementStatus = 'pending' | 'running' | 'paused_at_gate' | 'complete' | 'aborted'
export type GateStatus = 'gate_1' | 'gate_2' | 'gate_3' | 'complete'
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type TargetType = 'web' | 'local_codebase' | 'binary'
export type TriageStatus = 'unreviewed' | 'accepted' | 'false_positive' | 'fixed'

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
  // API returns these field names from the DB model
  vulnerability_class?: string
  attack_class?: string
  affected_surface?: string
  endpoint?: string
  description?: string
  evidence: string | string[]
  confidence_score: number
  triage_status?: TriageStatus
  triage_notes?: string
  triage_updated_at?: string | null
  triage_judgment?: TriageJudgment | null
  created_at: string
}

export interface AgentInfo {
  agent_id: string
  agent_type: string
  status: string
  engagement_id: string
}

export interface TriageJudgment {
  likely_false_positive: boolean
  confidence: number
  reasoning: string
  dedup_signature: string
  suggested_severity?: Severity | null
}

export interface SwarmEvent {
  type: 'agent_started' | 'agent_completed' | 'finding_discovered' | 'finding_judged' | 'agent_thought' | 'gate_triggered' | 'campaign_complete' | 'progress' | 'ping'
  payload: Record<string, unknown>
  timestamp: string
}

export interface ExploitStep {
  step: number
  title: string
  detail: string
  code?: string | null
}

export interface ExploitDetail {
  walkthrough: ExploitStep[]
  attack_path_mermaid: string
  impact: string
  prerequisites: string[]
  difficulty: 'easy' | 'medium' | 'hard'
}

export interface PoCDetail {
  language: string
  filename: string
  script: string
  setup: string[]
  notes: string
  sequence_diagram: string
}

export interface ExploitScript {
  language: string
  filename: string
  script: string
  setup: string[]
  patched_setup?: string[]
  patched_label?: string
  expected_output: string
  impact_achieved: string
}

export interface ExploitExecution {
  stdout: string
  stderr: string
  exit_code: number
  timed_out: boolean
  verdict: 'confirmed' | 'failed' | 'inconclusive'
  confidence: number
  reasoning: string
  executed_at: string
  override_verdict: 'confirmed' | 'failed' | 'inconclusive' | null
}

export interface ExecutionRunRaw {
  stdout: string
  stderr: string
  exit_code: number
  timed_out: boolean
  executed_at: string
}

export interface ExploitExecutionDiff {
  patched_label: string
  vuln_run: ExecutionRunRaw
  patched_run: ExecutionRunRaw
  verdict: 'confirmed' | 'failed' | 'inconclusive'
  confidence: number
  reasoning: string
  vuln_succeeded?: boolean | null
  patched_blocked?: boolean | null
}

export interface FindingDetail extends Finding {
  exploit_detail?: ExploitDetail | null
  poc_detail?: PoCDetail | null
  exploit_script?: ExploitScript | null
  exploit_execution?: ExploitExecution | null
  exploit_execution_diff?: ExploitExecutionDiff | null
  reproduction_steps?: string[]
  validation_status?: string
}
