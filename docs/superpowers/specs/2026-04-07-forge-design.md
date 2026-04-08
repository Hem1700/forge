# FORGE — Framework for Offensive Reasoning, Generation and Exploitation
**Design Document** · April 7, 2026

---

## Table of Contents

1. [Vision & Core Philosophy](#1-vision--core-philosophy)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Component Deep Dives](#4-component-deep-dives)
5. [The 5 Gaps — How FORGE Solves Them](#5-the-5-gaps--how-forge-solves-them)
6. [Data Models](#6-data-models)
7. [API Design](#7-api-design)
8. [Human Gates — UX Flow](#8-human-gates--ux-flow)
9. [Security & Ethics](#9-security--ethics)
10. [Project Structure](#10-project-structure)

---

## 1. Vision & Core Philosophy

**FORGE** is a hybrid autonomous pentesting platform powered by a two-tier cognitive architecture: a persistent **Strategic Brain** that accumulates knowledge across every engagement, and a **Tactical Swarm** of dynamic agents that self-organize, bid on tasks, spawn children, and terminate dead threads — all without human intervention until it matters.

Unlike every existing tool, FORGE doesn't start fresh on each engagement. It remembers. The tenth test is smarter than the first because the Brain encoded what worked, what failed, what evasion strategies succeeded against which stacks, and what business logic patterns led to confirmed findings. That compounding intelligence is FORGE's core moat.

### The Three Principles

1. **Reasoning over scanning** — FORGE doesn't pattern-match. It builds a semantic model of what a target *does* and derives attack hypotheses from business logic, not signatures.
2. **Emergence over orchestration** — the swarm composition isn't planned. It evolves as the target reveals itself.
3. **Trust nothing, validate everything** — no finding reaches a human without surviving an adversarial validation gauntlet.

### What FORGE Is For
- Bug bounty hunters running campaigns against programs
- Red teams running authorized engagements
- Security researchers stress-testing their own applications

### What FORGE Is Not
- A CVE scanner (use Nuclei for that)
- A point-and-click tool for beginners
- Authorized for use against targets you don't own or have explicit written permission to test

---

## 2. High-Level Architecture

FORGE has 5 major layers. Each has a clear boundary and communicates through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────┐
│                    FORGE PLATFORM                        │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              HUMAN INTERFACE LAYER               │   │
│  │   Web UI  ·  CLI  ·  Human Gates  ·  Reports    │   │
│  └─────────────────────┬───────────────────────────┘   │
│                        │                                │
│  ┌─────────────────────▼───────────────────────────┐   │
│  │              STRATEGIC BRAIN                     │   │
│  │  Knowledge Graph · Semantic Modeler · Campaign   │   │
│  │  Planner · Evasion Strategist · Memory Engine   │   │
│  └──────┬──────────────────────────────┬───────────┘   │
│         │                              │               │
│  ┌──────▼──────────┐        ┌──────────▼────────────┐  │
│  │   TASK BOARD    │        │   KNOWLEDGE STORE      │  │
│  │  (Shared State) │        │  Vector DB + Graph DB  │  │
│  └──────┬──────────┘        └───────────────────────┘  │
│         │                                              │
│  ┌──────▼──────────────────────────────────────────┐   │
│  │              TACTICAL SWARM                      │   │
│  │  Recon · Logic Modeler · Probe · Exploit ·       │   │
│  │  Evasion · Child Agents · Swarm Scheduler        │   │
│  └──────────────────┬───────────────────────────────┘   │
│                     │                                   │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │           ADVERSARIAL VALIDATOR                   │  │
│  │   Challenger · Context · Severity · Confidence   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Layer 1 — Human Interface Layer

Two surfaces: a **Web UI** (React + TypeScript) for campaign management, live swarm monitoring, human gate approvals, and report viewing, and a **CLI** for power users who want to run FORGE headlessly or integrate it into pipelines.

The human gates live here — three decision points where the system pauses and waits for human input before proceeding. Everything else runs autonomously.

### Layer 2 — Strategic Brain

The always-on intelligence core. Never resets between engagements. Has 4 sub-components:

- **Semantic Modeler** — takes raw target input, builds a structured model of what the app does (endpoints, user roles, business flows, trust boundaries)
- **Campaign Planner** — queries the knowledge store, generates prioritized attack hypotheses for this specific target
- **Evasion Strategist** — fingerprints the defensive stack (WAF, rate limits, IDS patterns) and produces stealth guidelines the swarm follows
- **Memory Engine** — after each engagement, extracts lessons learned and writes them back into the knowledge store

The Brain communicates with the Tactical Swarm exclusively through the Task Board. It doesn't directly control agents — it writes tasks and the swarm self-organizes to execute them.

### Layer 3 — Task Board + Knowledge Store

**Task Board:** an event-sourced, conflict-safe shared blackboard. Agents read from it, write to it, and bid on tasks. Every mutation is an immutable event — full audit trail of everything the swarm did and why.

**Knowledge Store:** two databases behind one query interface:
- **Qdrant** (vector DB) — semantic similarity search: *"what techniques worked against apps that look like this one?"*
- **Neo4j** (graph DB) — relational reasoning: *"what is the full attack chain from this entry point to this impact?"*

### Layer 4 — Tactical Swarm

The dynamic agent population. Six agent archetypes:

| Agent Type | Responsibility |
|---|---|
| **Recon Agent** | Surface discovery, tech fingerprinting, endpoint mapping |
| **Logic Modeler Agent** | Behavioral crawling, semantic trust model construction |
| **Probe Agent** | Tests a single hypothesis with minimal noise |
| **Evasion Agent** | Models defensive stack, advises stealth strategies |
| **Deep Exploit Agent** | Full exploitation chains — only spawned post-human-approval |
| **Child Agent** | Spawned by any agent to pursue a sub-thread |

Plus a **Swarm Scheduler** that runs the bidding auction, tracks agent lineage, monitors thread health, and reallocates resources from dead threads to live ones.

### Layer 5 — Adversarial Validator

A gauntlet every finding must survive before reaching a human gate:

1. **Challenger Agent** — independently reproduces the finding from scratch
2. **Context Agent** — verifies scope compliance, checks against known false positive patterns
3. **Severity Agent** — independently assesses impact using CVSS + semantic app model
4. **Confidence Scorer** — produces a final 0–1 confidence score; only findings scoring ≥0.75 proceed to a human gate

### Data Flow — One Full Engagement

```
Target Input
    → Semantic Modeler builds app model
    → Campaign Planner generates hypotheses → Task Board populated
    → Swarm Scheduler spins up initial agents
    → Agents bid on tasks, execute, write findings + new tasks
    → Thread Health Monitor kills dead threads, reallocates
    → [HUMAN GATE 1: approve campaign scope]
    → Swarm continues, adapts, spawns children
    → Probe Agents surface candidate findings
    → [HUMAN GATE 2: approve exploitation targets]
    → Deep Exploit Agents confirm + document
    → Adversarial Validator gauntlet
    → Validated findings → Report Agent
    → [HUMAN GATE 3: approve final report]
    → Engagement closes → Memory Engine writes to Knowledge Store
```

---

## 3. Tech Stack

### Strategic Brain
| Component | Technology | Why |
|---|---|---|
| LLM backbone | Claude Sonnet 4.6 via Anthropic API | Best reasoning for semantic modeling and campaign planning |
| Local LLM option | Ollama + Llama 3.3 70B | Privacy-first option for sensitive engagements |
| Vector DB | Qdrant | Fast semantic search, self-hostable, excellent Python SDK |
| Graph DB | Neo4j | Industry standard for attack chain relationship modeling |
| Memory orchestration | LangChain + LangGraph | Agent memory, retrieval chains, graph-based agent workflows |

### Tactical Swarm
| Component | Technology | Why |
|---|---|---|
| Agent framework | LangGraph | Native support for stateful multi-agent graphs with branching |
| Task Board | Redis Streams | Event-sourced, conflict-safe, sub-millisecond pub/sub |
| Agent communication | Redis pub/sub | Lightweight, fast inter-agent messaging |
| Recon tooling | httpx, subfinder, ffuf, nuclei, katana | Best-in-class open source recon tools, Python-callable |
| Exploit tooling | pwntools, requests, custom payloads | Flexible exploit chain construction |
| Browser automation | Playwright | JS-heavy app crawling, auth flow walking |

### Backend
| Component | Technology | Why |
|---|---|---|
| API server | FastAPI | Async, fast, excellent for streaming agent output to UI |
| Task queue | Celery + Redis | Long-running agent tasks, retry logic |
| Database | PostgreSQL | Engagement records, findings, audit logs |
| ORM | SQLAlchemy + Alembic | Schema migrations, clean models |
| Auth | JWT + bcrypt | Secure API access |

### Frontend
| Component | Technology | Why |
|---|---|---|
| Framework | React + TypeScript | Type-safe, component-driven UI |
| Build tool | Vite | Fast dev experience |
| UI components | shadcn/ui + Tailwind | Clean, accessible, fast to build with |
| Real-time updates | WebSockets | Live swarm activity feed, agent status |
| State management | Zustand | Lightweight, no boilerplate |
| Charts/graphs | Recharts | Attack graph visualization |

### Infrastructure
| Component | Technology | Why |
|---|---|---|
| Containerization | Docker + Docker Compose | Reproducible local + cloud deployment |
| Orchestration | Kubernetes (optional) | Scale swarm agents horizontally in cloud deployments |
| Secrets | HashiCorp Vault / env files | Secure API key management |
| Logging | structlog + OpenTelemetry | Full observability on agent behavior |

---

## 4. Component Deep Dives

### 4.1 Dynamic Swarm Composition

**The Task Board (Shared Blackboard)**

The Brain doesn't assign agents to agents. It writes to a shared **Task Board** — a live, continuously updated data structure:

```
[TASK-042] Test JWT signature validation bypass
  Surface: /api/auth/refresh
  Hypothesis: alg:none attack possible based on library version fingerprint
  Confidence needed: >0.70
  Priority: HIGH
  Spawned by: Recon Agent #3
  Status: OPEN

[TASK-043] Enumerate S3 bucket permissions
  Surface: static.target.com → resolves to AWS S3
  Hypothesis: bucket misconfiguration, public write possible
  Confidence needed: >0.60
  Priority: MEDIUM
  Spawned by: Brain (knowledge graph hit: 41% of similar stacks had this)
  Status: OPEN
```

Any agent can read the board. Any agent can write to the board. Tasks can be created by the Brain, by agents, or by child agents.

**The Bidding System**

When a task hits the board, available agents evaluate it and submit a bid:

```
Agent: WebProbe-7
Task: TASK-042 (JWT bypass)
Bid confidence: 0.83
Basis: 12 successful JWT tests in knowledge graph, 3 against same library version
Estimated probes needed: 4-6
Estimated noise generated: LOW
```

The Swarm Scheduler runs a lightweight auction:
- Highest confidence bid wins, ties broken by noise estimate (prefer quieter agents)
- If no agent bids above the required threshold, the Brain spawns a new specialized agent
- Multiple high-confidence bids → parallel competition mode (two agents race, first to validate wins, other becomes adversarial validation)

**Agent Spawning and Lineage**

Every agent has a lineage — a parent, a spawning reason, and a termination condition:

```
Brain
└── ReconAgent-1 (spawned: engagement start, terminate: after surface map complete)
    └── JSAnalyzer-4 (spawned: large JS bundle found, terminate: after API endpoint extraction)
        └── AuthFlowMapper-9 (spawned: non-standard auth pattern detected, terminate: after flow modeled)
            └── ProbeAgent-14 (spawned: TASK-042 won bid, terminate: after hypothesis confirmed/rejected)
```

**Thread Health Monitor**

- Every agent emits a signal score after each action: 0 (dead end) to 1 (promising)
- Signal scores tracked over a rolling window
- Rolling average drops below 0.2 for 5 consecutive actions → automatic termination
- Final state written to knowledge graph before termination
- Resources reallocated to highest-priority open tasks

**Swarm State Over Time — Example 4-Hour Engagement**

```
Hour 0:00  →  Brain spawns 4 Recon Agents, 1 Logic Modeler
Hour 0:45  →  Recon complete. Brain spawns 8 Probe Agents targeting top hypotheses
Hour 1:30  →  3 Probe Agents hit dead ends → terminated. 2 spawn children for deeper threads.
             JSAnalyzer child discovers GraphQL introspection enabled → new task board entry
             Brain spawns GraphQL-specialized Probe Agent (never planned at start)
Hour 2:15  →  GraphQL Agent finds IDOR. Writes CRITICAL task. Swarm now at 11 agents.
             Human Gate #2 triggered → awaiting approval
Hour 2:30  →  Human approves. Deep Exploit Agent spawned.
Hour 3:45  →  5 confirmed findings. Adversarial Validator kills 2 as false positives.
             3 survive with evidence packages. Report Agent spawned.
Hour 4:00  →  Human Gate #3. Report delivered.
```

---

## 5. The 5 Gaps — How FORGE Solves Them

| Gap | Industry Status | How FORGE Solves It |
|---|---|---|
| **Cross-engagement learning** | All tools start fresh every engagement | Strategic Brain's knowledge graph + vector memory persists and compounds across every engagement |
| **Semantic business logic reasoning** | All tools hunt CVEs and OWASP signatures | Logic Modeler Agents + semantic trust model → novel hypotheses no scanner can generate |
| **Dynamic swarm composition** | Fixed agent roles hardcoded at design time | Agents bid on tasks, spawn children, self-terminate — composition evolves mid-engagement |
| **Adversarial validation** | Tools report findings, no internal skeptic | Challenger/Context/Severity agents kill false positives before humans see them |
| **Evasion-aware testing** | No tool models the defensive stack | Evasion Agents fingerprint WAF/IDS/rate limits and advise the swarm on stealth strategies |

---

## 6. Data Models

### Engagement
```python
Engagement:
  id: UUID
  target_url: str
  target_scope: list[str]
  target_out_of_scope: list[str]
  status: Enum[pending, running, paused_at_gate, complete, aborted]
  gate_status: Enum[gate_1, gate_2, gate_3, complete]
  semantic_model: JSON
  campaign_hypotheses: list[Hypothesis]
  findings: list[Finding]
  created_at: datetime
  completed_at: datetime | None
```

### Hypothesis
```python
Hypothesis:
  id: UUID
  engagement_id: UUID
  title: str
  surface: str
  attack_class: str
  reasoning: str
  confidence: float
  priority: Enum[critical, high, medium, low]
  source: Enum[brain, agent, child_agent]
  spawned_by: UUID | None
  status: Enum[open, assigned, confirmed, rejected, invalidated]
  assigned_to: UUID | None
  created_at: datetime
```

### Agent
```python
Agent:
  id: UUID
  engagement_id: UUID
  type: Enum[recon, logic_modeler, probe, evasion, deep_exploit, child, validator]
  parent_id: UUID | None
  spawned_reason: str
  status: Enum[idle, bidding, running, terminated, completed]
  current_task_id: UUID | None
  signal_history: list[float]
  termination_reason: str | None
  tools: list[str]
  created_at: datetime
  terminated_at: datetime | None
```

### Task
```python
Task:
  id: UUID
  engagement_id: UUID
  hypothesis_id: UUID | None
  title: str
  description: str
  surface: str
  required_confidence: float
  priority: Enum[critical, high, medium, low]
  status: Enum[open, bidding, assigned, awaiting_human_gate, complete, rejected]
  bids: list[Bid]
  assigned_agent_id: UUID | None
  result: TaskResult | None
  created_by: UUID
  created_at: datetime
  event_log: list[TaskEvent]
```

### Bid
```python
Bid:
  id: UUID
  task_id: UUID
  agent_id: UUID
  confidence: float
  basis: str
  estimated_probes: int
  noise_level: Enum[low, medium, high]
  submitted_at: datetime
  outcome: Enum[won, lost, expired] | None
```

### Finding
```python
Finding:
  id: UUID
  engagement_id: UUID
  task_id: UUID
  agent_id: UUID
  title: str
  description: str
  vulnerability_class: str
  affected_surface: str
  reproduction_steps: list[str]
  evidence: list[Evidence]
  cvss_score: float | None
  severity: Enum[critical, high, medium, low, info]
  validation_status: Enum[pending, validated, rejected]
  validation_report: ValidationReport | None
  confidence_score: float
  created_at: datetime
```

### KnowledgeGraphEntry
```python
KnowledgeGraphEntry:
  id: UUID
  engagement_id: UUID
  tech_stack: list[str]
  app_type: str
  attack_class: str
  technique: str
  outcome: Enum[confirmed, false_positive, inconclusive]
  evasion_used: str | None
  signal_strength: float
  notes: str
  created_at: datetime
```

---

## 7. API Design

All endpoints under `/api/v1`. FastAPI with JWT auth on every route.

### Engagements
```
POST   /api/v1/engagements
GET    /api/v1/engagements
GET    /api/v1/engagements/{id}
DELETE /api/v1/engagements/{id}

GET    /api/v1/engagements/{id}/status
GET    /api/v1/engagements/{id}/agents
GET    /api/v1/engagements/{id}/tasks
GET    /api/v1/engagements/{id}/findings
GET    /api/v1/engagements/{id}/report
```

### Human Gates
```
GET    /api/v1/engagements/{id}/gates/{gate_number}
POST   /api/v1/engagements/{id}/gates/{gate_number}/approve
POST   /api/v1/engagements/{id}/gates/{gate_number}/reject
```

### Knowledge Store
```
GET    /api/v1/knowledge/search?q=&tech_stack=&app_type=
GET    /api/v1/knowledge/stats
DELETE /api/v1/knowledge/{entry_id}
```

### WebSocket
```
WS     /ws/engagements/{id}/stream
# Events: agent_spawned, agent_terminated, task_created,
#         task_assigned, task_closed, finding_surfaced, gate_triggered
```

### System
```
GET    /api/v1/health
GET    /api/v1/models
PUT    /api/v1/settings
```

---

## 8. Human Gates — UX Flow

### Gate 1 — Recon Summary
System presents: surface map, semantic app model, top 10 hypotheses with reasoning, estimated duration and noise level.

Human decisions: approve as-is, remove hypotheses from scope, add out-of-scope rules, adjust stealth level (aggressive / balanced / quiet).

### Gate 2 — Pre-Exploitation
System presents each validated finding: title, severity, surface, reproduction steps, evidence, confidence score, proposed exploitation chain.

Human decisions per finding: approve full exploitation, approve with depth limit, skip, or reject as false positive.

### Gate 3 — Report Sign-Off
System presents: executive summary, all confirmed findings with severity/CVSS/evidence, attack chain visualization, remediation recommendations, MITRE ATT&CK mapping.

Human decisions: approve and export (PDF/markdown/JSON), request edits, trigger re-test.

---

## 9. Security & Ethics

- Explicit written authorization required before any engagement starts (scope doc upload is mandatory)
- All data stays local by default — cloud LLM calls are opt-in per engagement
- Full audit log of every agent action, probe sent, and payload used — exportable for legal/compliance
- Safe mode: recon-only, no active probes beyond passive fingerprinting
- No engagement can run against `localhost`, RFC1918 ranges, or `.gov`/`.mil` TLDs without explicit override flag
- Knowledge store entries are scoped per user — no cross-user data leakage

---

## 10. Project Structure

```
forge/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── engagements.py
│   │   │   ├── gates.py
│   │   │   ├── knowledge.py
│   │   │   └── system.py
│   │   ├── brain/
│   │   │   ├── semantic_modeler.py
│   │   │   ├── campaign_planner.py
│   │   │   ├── evasion_strategist.py
│   │   │   └── memory_engine.py
│   │   ├── swarm/
│   │   │   ├── scheduler.py
│   │   │   ├── task_board.py
│   │   │   ├── agents/
│   │   │   │   ├── base.py
│   │   │   │   ├── recon.py
│   │   │   │   ├── logic_modeler.py
│   │   │   │   ├── probe.py
│   │   │   │   ├── evasion.py
│   │   │   │   ├── deep_exploit.py
│   │   │   │   └── child.py
│   │   │   └── health_monitor.py
│   │   ├── validator/
│   │   │   ├── challenger.py
│   │   │   ├── context.py
│   │   │   ├── severity.py
│   │   │   └── scorer.py
│   │   ├── knowledge/
│   │   │   ├── vector_store.py
│   │   │   ├── graph_store.py
│   │   │   └── query.py
│   │   ├── models/
│   │   │   ├── engagement.py
│   │   │   ├── agent.py
│   │   │   ├── task.py
│   │   │   ├── finding.py
│   │   │   └── knowledge.py
│   │   └── ws/
│   │       └── stream.py
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── EngagementDashboard/
│   │   │   ├── SwarmMonitor/
│   │   │   ├── HumanGate/
│   │   │   ├── FindingsPanel/
│   │   │   └── ReportViewer/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── store/
│   │   └── types/
│   └── package.json
│
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-07-forge-design.md
│
├── docker-compose.yml
├── Makefile
└── README.md
```
