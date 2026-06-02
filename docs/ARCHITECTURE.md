# FORGE — Architecture & System Design

## System Diagram

```
  Browser / forge CLI
        │  HTTP + WebSocket
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                  FastAPI  (port 8080)                       │
  │                                                             │
  │  REST routers: auth · engagements · findings · gates        │
  │                knowledge · system · start                   │
  │                org_admin · super_admin                      │
  │                                                             │
  │  WS /ws/{engagement_id}  ← JWT/API-key auth, org-scoped,   │
  │                             event replay on reconnect       │
  │                                                             │
  │  Startup: sweep orphaned engagements (worker crash recovery)│
  └──────────────────────┬──────────────────────┬──────────────┘
                         │ SQLAlchemy async      │ pub/sub + queue
                         ▼                       ▼
              ┌─────────────────┐     ┌─────────────────────────┐
              │   PostgreSQL    │     │          Redis           │
              │                 │     │                          │
              │ users · orgs    │     │  Arq job queue           │
              │ api_keys        │     │  └─ engagement pipelines │
              │ engagements     │     │                          │
              │ findings        │     │  pub/sub bridge          │
              │ tasks · agents  │     │  └─ live event fan-out   │
              │ events          │     │     to all WS clients    │
              │ knowledge       │     └───────────┬─────────────┘
              └─────────────────┘                 │
                                                  ▼
                                    ┌─────────────────────────────┐
                                    │       Arq Worker            │
                                    │  arq app.worker.WorkerSettings│
                                    │                             │
                                    │  run_web_pipeline           │
                                    │    SemanticModeler          │
                                    │    → CampaignPlanner        │
                                    │    → ProbeAgents (parallel) │
                                    │    → FindingsJudge          │
                                    │                             │
                                    │  run_codebase_pipeline      │
                                    │    CodebaseModeler          │
                                    │    → CodeAnalyzer           │
                                    │    → DependencyScanner      │ (parallel)
                                    │    → Fuzzer                 │
                                    │    → SecretScanner          │
                                    │    → ConfigAuditor          │
                                    │                             │
                                    │  run_os_pipeline            │
                                    │    OSModeler (SSH collect)  │
                                    │    → PrivEscAgent           │
                                    │    → ServiceAuditAgent      │ (parallel)
                                    │    → PackageVulnAgent       │
                                    │    → ConfigAuditAgent       │
                                    │    → NetworkExposureAgent   │
                                    │    → ChainDiscoveryAgent    │
                                    │                             │
                                    │  judge_findings             │
                                    │    FindingsJudge            │
                                    │    (LLM verdict + dedup)    │
                                    │                             │
                                    │  Cron: reset_monthly_budgets│
                                    │        refresh_trivy_db     │
                                    │        refresh_nvd_cache    │
                                    └─────────────────────────────┘

  Strategic Brain (app/brain/)
  ├── SemanticModeler      crawl + model web app surfaces
  ├── CodebaseModeler      parse source, map logic + deps
  ├── OSModeler            SSH fingerprint collection (agentless)
  ├── CampaignPlanner      LLM attack hypothesis generation
  ├── ExploitEngine        walkthrough + Mermaid attack path
  ├── PoCEngine            runnable PoC script + sequence diagram
  ├── ExploitScriptEngine  weaponized exploit script
  ├── ExploitExecutor      Docker sandboxed execution
  ├── ExecutionJudge       LLM verdict (confirmed / failed / inconclusive)
  ├── ContextManager       token counting + message compression
  └── Researcher           OSV/NVD CVE advisory fetch

  Tactical Swarm (app/swarm/)
  Web/Codebase: Recon · Probe · CodeAnalyzer · DependencyScanner
                Fuzzer · SecretScanner · ConfigAuditor · DeepExploit · Evasion
  OS Scanning:  PrivEscAgent · ServiceAuditAgent · PackageVulnAgent
                ConfigAuditAgent · NetworkExposureAgent · ChainDiscoveryAgent
  Scheduler (auction-based bid) → TaskBoard → HealthMonitor

  Knowledge Engine
  ├── Qdrant   vector similarity (cross-engagement technique recall)
  └── Neo4j    attack-pattern knowledge graph

  External
  ├── LLM Providers   Anthropic · OpenAI · AWS Bedrock · Azure OpenAI
  │                   (per-org keys; factory resolves at call time)
  ├── Docker          sandboxed exploit execution
  └── OSV / NVD APIs  CVE research
```

---

## Components

### Auth Layer

JWT + API key dual authentication, 4-tier RBAC, org-scoped data isolation on every route.

| Role | Capabilities |
|------|-------------|
| `viewer` | Read engagements, findings, events |
| `analyst` | Viewer + create/start engagements, triage, generate exploits/PoC/report |
| `admin` | Analyst + manage org users and roles, delete engagements |
| `super_admin` | Admin + cross-org user management and provisioning |

### TrackedLLM — Production-Hardening Layers

`TrackedLLM` wraps every LLM call with five production-hardening layers:

1. **Budget enforcement** — per-org monthly spend cap with hard-block or warn mode; HTTP 402 on breach
2. **Rate limiting** — per-provider sliding-window TPM/RPM limits in Redis via atomic Lua scripts; HTTP 429 with `Retry-After` on exhaustion
3. **Tier-based model routing** — 20 task types mapped to LIGHT/STANDARD/HEAVY tiers, auto-selecting Haiku/Sonnet/Opus (or provider equivalent) without manual configuration
4. **Context compression** — automatic message-window management with LLM-assisted summarisation when context exceeds 70% of model limit
5. **Prompt caching** — client-side Redis response cache (SHA256-keyed, per-task TTLs) plus Anthropic native `cache_control` for server-side KV reuse

### Tier-Based Model Routing

Without any explicit configuration, FORGE maps every task type to a LIGHT / STANDARD / HEAVY tier:

| Tier | Anthropic | OpenAI | Purpose |
|------|-----------|--------|---------|
| LIGHT | claude-haiku-4-5 | gpt-4o-mini | Summarisation, classification, recon |
| STANDARD | claude-sonnet-4-6 | gpt-4o | Analysis, planning, audit |
| HEAVY | claude-opus-4-7 | o1 | Exploit generation, chain discovery, execution judging |

OS scanning: `privesc_analysis` and `chain_discovery` use HEAVY; the remaining four use STANDARD.

View the effective routing table:

```bash
forge org llm tiers
```

### Knowledge Engine

- **Qdrant** — vector similarity search for cross-engagement technique recall
- **Neo4j** — attack-pattern knowledge graph; used by `ChainDiscoveryAgent` for graph traversal with in-memory DFS fallback

#### Neo4j Schema

Two graph schemas are maintained: a global `:Technique` knowledge graph (cross-engagement, persistent) and a per-scan `:OsFinding` engagement graph (ephemeral, written by `ChainDiscoveryAgent`). Both graphs use `ENABLES` / `LEADS_TO` directed relationships for path traversal. Full node labels, property names, relationship rules, and Cypher examples are documented in [docs/neo4j-schema.md](neo4j-schema.md).

---

## OS Pipeline — Agent Detail

The OS pipeline fingerprints a live Linux host over SSH (agentless — read-only commands only) then runs six agents:

1. **OSModeler** — connects via `asyncssh`, runs 18 read-only commands in parallel (kernel, packages, processes, open ports, SUID binaries, sudo rules, cron jobs, sysctl, users/groups, SSH config, PAM, mounts, login history), returns a structured `OSFingerprint` in under 30 seconds

2. **PrivEscAgent** — checks SUID binaries against a built-in GTFOBins database, LLM-analyses sudo rules for NOPASSWD/wildcard exploits, cross-references writable paths against root-owned cron jobs, checks docker group membership and NFS `no_root_squash`

3. **ServiceAuditAgent** — audits SSH hardening settings (PermitRootLogin, PasswordAuthentication, weak ciphers/MACs/KEX), detects services running as root, flags cleartext protocols (telnet, FTP, rsh) and exposed unauthenticated management interfaces (Redis, Postgres, Elasticsearch, etc.)

4. **PackageVulnAgent** — runs Trivy against the installed package list (Trivy DB refreshed daily via Arq cron), enriches high-CVSS CVEs with LLM exploitability-in-context scoring

5. **ConfigAuditAgent** — checks sysctl parameters (ASLR, ptrace scope, SYN cookies, IP forwarding), PAM lockout policy, `/tmp` mount flags, and NFS exports

6. **NetworkExposureAgent** — builds an external exposure matrix, detects IPv6-only bindings that may bypass IPv4 firewall rules, and cross-correlates root-owned + internet-facing + unauthenticated services into CRITICAL findings

7. **ChainDiscoveryAgent** — correlates findings from all five agents into multi-step attack chains using Neo4j graph traversal (with in-memory DFS fallback). Surfaces paths that appear low-risk in isolation but combine into a root escalation — e.g., writable `/etc/cron.d/` + SUID `vim` + weak sudo rule.

---

## LLM Provider Configuration

Each org can bring its own LLM provider and API key. FORGE supports **Anthropic** (Claude), **OpenAI** (GPT), **AWS Bedrock**, and **Azure OpenAI** — all org-scoped with Fernet-encrypted key storage and per-task model overrides.

### Supported providers

| Provider | Key type | Notes |
|----------|----------|-------|
| `anthropic` | `api_key` | Claude Sonnet / Haiku / Opus |
| `openai` | `api_key` | GPT-4 Turbo / GPT-4o-mini |
| `bedrock` | IAM role (recommended) or static key | Set `--iam-role` for role-based auth |
| `azure` | `api_key` + `endpoint` | Azure OpenAI deployment URL required |

### Configuring credentials

```bash
# Store an Anthropic key
forge org llm key set anthropic
# → API key for anthropic: ****
# → ✓ Credentials for anthropic saved.

# Use an IAM role for Bedrock (no key needed)
forge org llm key set bedrock --iam-role --region us-east-1

# Azure OpenAI (key + endpoint)
forge org llm key set azure --endpoint https://myorg.openai.azure.com

# Validate credentials with a 1-token probe
forge org llm key test anthropic

# Revoke credentials
forge org llm key revoke openai --yes
```

### Viewing the current configuration

```bash
forge org llm show
```

```
╭─ AI Provider Configuration ──────────────────────────────╮
│ Active credentials                                        │
│   ✓ anthropic   configured · last tested 2026-05-18      │
│   ✓ bedrock     IAM role · us-east-1                     │
│   ✗ openai      not configured                           │
│   ✗ azure       not configured                           │
│                                                           │
│ Preset: balanced                                          │
╰───────────────────────────────────────────────────────────╯
 Task                  Provider    Model                Source
 agent_brain           anthropic   claude-sonnet-4-6    default
 campaign_planning     anthropic   claude-sonnet-4-6    default
 findings_judge        anthropic   claude-haiku-4-5     default
 ...
```

### Model presets

```bash
forge org llm preset smart      # Best models for all tasks
forge org llm preset balanced   # Forge defaults (mix of capable + cheap)
forge org llm preset cheap      # Lowest-cost models for all tasks
```

### Per-task overrides

```bash
forge org llm set findings_judge --provider openai --model gpt-4-turbo
forge org llm set agent_brain --provider bedrock --model anthropic.claude-sonnet-4 --max-tokens 4096
```

Task types: `codebase_modeling`, `campaign_planning`, `code_analyzer`, `semantic_modeler`, `findings_judge`, `execution_judge`, `exploit_engine`, `exploit_script`, `poc_engine`, `evasion_strategist`, `logic_modeler`, `agent_brain`, `challenger`, `severity_assessor`, `privesc_analysis`, `service_audit`, `package_vuln_analysis`, `config_audit`, `network_exposure`, `chain_discovery`

### Usage and cost tracking

```bash
forge org llm usage
forge org llm usage --since 2026-05-01T00:00:00
```

```
 Task               Provider    Model                 Calls  Input tokens  Output tokens  Cost (USD)
 findings_judge     anthropic   claude-haiku-4-5        142       284,000         71,000     $0.0426
 campaign_planning  anthropic   claude-sonnet-4-6        24        96,000         24,000     $0.3600
 ...

Total: $0.4026
```

### LLM REST API

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/org/llm/providers` | any | List supported providers and required fields |
| `GET` | `/api/v1/org/llm/credentials` | any | List configured providers (keys never returned) |
| `PUT` | `/api/v1/org/llm/credentials/{provider}` | admin | Store or update credentials |
| `POST` | `/api/v1/org/llm/credentials/{provider}/test` | admin | Validate credentials with a 1-token probe |
| `DELETE` | `/api/v1/org/llm/credentials/{provider}` | admin | Revoke stored credentials |
| `GET` | `/api/v1/org/llm/task-config` | any | Get task → model mapping (with preset detection) |
| `PUT` | `/api/v1/org/llm/task-config` | admin | Apply preset or custom task config |
| `GET` | `/api/v1/org/llm/usage` | any | Aggregated token usage and cost |
| `GET` | `/api/v1/org/llm/audit` | admin | Credential change audit log |

Credential storage: API keys are Fernet-symmetric-encrypted before writing to the database. The plaintext key is never stored or returned — only a `configured: true/false` flag is exposed. Encryption requires `FORGE_SECRETS_KEY` to be set in `.env`.

---

## Full API Reference

All endpoints (except `/health` and `/auth/register`/`/auth/login`) require `Authorization: Bearer <token>`.

### Auth & users

| Method | Path | Role required | Description |
|--------|------|---------------|-------------|
| `POST` | `/api/v1/auth/register` | — | Register (first user = super_admin) |
| `POST` | `/api/v1/auth/login` | — | Get JWT |
| `GET` | `/api/v1/auth/me` | any | Current user info |
| `GET` | `/api/v1/auth/api-keys` | any | List own API keys |
| `POST` | `/api/v1/auth/api-keys` | any | Create API key |
| `DELETE` | `/api/v1/auth/api-keys/{id}` | any | Revoke API key |
| `GET` | `/api/v1/org/users` | admin | List org users |
| `PATCH` | `/api/v1/org/users/{id}/role` | admin | Update user role (max = admin) |
| `DELETE` | `/api/v1/org/users/{id}` | admin | Remove user |
| `GET` | `/api/v1/admin/users` | super_admin | List all users |
| `PATCH` | `/api/v1/admin/users/{id}/role` | super_admin | Set any role |
| `POST` | `/api/v1/admin/provision` | super_admin | Provision user with role |

### Engagements & findings

| Method | Path | Role required | Description |
|--------|------|---------------|-------------|
| `GET` | `/api/v1/health` | — | API liveness check |
| `GET` | `/api/v1/health/worker` | — | Arq worker liveness — `{status: up\|down\|unknown, stats}` |
| `POST` | `/api/v1/engagements/` | analyst | Create engagement |
| `GET` | `/api/v1/engagements/` | viewer | List engagements |
| `GET` | `/api/v1/engagements/{id}` | viewer | Get engagement |
| `PATCH` | `/api/v1/engagements/{id}/status` | analyst | Update status (`pending`, `running`, `aborted`) |
| `DELETE` | `/api/v1/engagements/{id}` | admin | Delete engagement (cascades findings, tasks, agents, events, knowledge) |
| `POST` | `/api/v1/engagements/{id}/start` | analyst | Launch the full pipeline |
| `GET` | `/api/v1/engagements/{id}/findings` | viewer | List findings |
| `GET` | `/api/v1/engagements/{id}/events` | viewer | Replay swarm events (latest 500) |
| `POST` | `/api/v1/engagements/{id}/report/pdf` | analyst | Generate PDF report |
| `POST` | `/api/v1/engagements/{id}/os-target` | analyst | Register SSH target + start OS pipeline |
| `POST` | `/api/v1/gates/{id}/decide` | analyst | Approve or reject human gate |
| `GET` | `/api/v1/findings/{id}` | viewer | Get full finding detail |
| `PATCH` | `/api/v1/findings/{id}/triage` | analyst | Triage decision |
| `POST` | `/api/v1/findings/{id}/exploit` | analyst | Generate (or return cached) exploit walkthrough |
| `GET` | `/api/v1/findings/{id}/poc` | viewer | Get PoC detail (null if not yet generated) |
| `POST` | `/api/v1/findings/{id}/poc` | analyst | Generate (or return cached) PoC script + sequence diagram |
| `POST` | `/api/v1/findings/{id}/exploit-script` | analyst | Generate weaponized exploit script |
| `POST` | `/api/v1/findings/{id}/execute` | analyst | Execute weaponized script against target (sandboxed) |
| `GET` | `/api/v1/knowledge/` | viewer | List knowledge base entries |
| `GET` | `/api/v1/knowledge/attack-class/{class}` | viewer | Filter knowledge by attack class |
| `GET` | `/api/v1/system/stats` | viewer | Engagement / finding / knowledge counts |
| `WS` | `/ws/{engagement_id}` | — | Live swarm event stream |

Full interactive docs: `http://localhost:8080/docs`

---

## Target Types

### Web Application

Tests HTTP endpoints — crawls the app, builds a semantic model, runs probe/recon/evasion agents.

```json
{
  "target_url": "https://example.com",
  "target_type": "web",
  "target_scope": ["/api", "/admin"],
  "target_out_of_scope": ["/static"]
}
```

### Local Codebase

Analyzes source code on the FORGE server's filesystem. Runs three agents in parallel:

- **CodeAnalyzer** — LLM-powered review for SQLi, command injection, path traversal, hardcoded secrets, prompt injection, sandbox escapes, and more
- **DependencyScanner** — checks `requirements.txt` / `package.json` / `go.mod` against the OSV CVE database (no API key needed)
- **Fuzzer** — generates malformed inputs, runs the CLI, detects crashes and hangs

```json
{
  "target_url": "local",
  "target_type": "local_codebase",
  "target_path": "/absolute/path/to/project"
}
```

### Binary

Analyzes a compiled binary file (ELF, PE, Mach-O). Same agents as local codebase, focused on the binary and any surrounding source.

```json
{
  "target_url": "local",
  "target_type": "binary",
  "target_path": "/absolute/path/to/binary"
}
```

### OS / Linux Host

Fingerprints a live Linux host over SSH and runs six purpose-built agents in parallel. No agent is deployed to the target — all collection is read-only via standard SSH commands.

```json
{
  "target_url": "local",
  "target_type": "os"
}
```

See the [OS Pipeline section](#os-pipeline--agent-detail) above for full agent descriptions.

---

## Project Structure

```
FORGE/
├── backend/
│   ├── app/
│   │   ├── api/          # REST endpoints
│   │   │   ├── auth.py         # register, login, GET /me
│   │   │   ├── api_keys.py     # API key CRUD
│   │   │   ├── deps.py         # get_current_user, require_analyst/admin/super_admin
│   │   │   ├── org_admin.py    # list/update/delete org users (admin+)
│   │   │   ├── org_llm.py      # /api/v1/org/llm/* — provider creds, task config, usage, audit
│   │   │   ├── super_admin.py  # cross-org management (super_admin only)
│   │   │   └── engagements, findings, gates, knowledge, system, start
│   │   ├── brain/        # SemanticModeler, CodebaseModeler, OSModeler, CampaignPlanner, ExploitEngine, PoCEngine, MemoryEngine
│   │   │   ├── llm_factory.py      # multi-provider get_llm(), RetryLLM, TrackedLLM (budget · rate limit · tier routing)
│   │   │   ├── context_manager.py  # token counting + message compression
│   │   │   ├── os_modeler.py       # asyncssh fingerprint collection
│   │   │   └── os_fingerprint.py   # OSFingerprint dataclass
│   │   ├── knowledge/    # Vector store (Qdrant) + graph store (Neo4j)
│   │   ├── models/       # SQLAlchemy ORM models (user, api_key, engagement, finding, task, agent,
│   │   │                 #   knowledge, org_llm, llm_usage)
│   │   ├── swarm/        # Agents, scheduler, health monitor, task board
│   │   │   └── agents/   # Web/codebase: recon, probe, evasion, code_analyzer, dependency_scanner, fuzzer, deep_exploit
│   │   │                 # OS scanning: privesc_agent, service_audit_agent, package_vuln_agent,
│   │   │                 #              config_audit_agent, network_exposure_agent, chain_discovery_agent
│   │   ├── validator/    # Challenger, context filter, severity scorer
│   │   ├── ws/           # WebSocket stream manager + Redis pub/sub bridge
│   │   ├── queue.py      # ArqRedis pool + enqueue/job_status helpers
│   │   └── worker.py     # Arq WorkerSettings — runs engagement pipelines out-of-process
│   ├── alembic/          # Database migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/          # Typed API clients (auth, engagements, findings, gates)
│       ├── components/   # EngagementDashboard, SwarmMonitor, HumanGate, FindingsPanel,
│       │                 # ExploitWalkthrough, AttackPathDiagram, PoCScript, ReportViewer
│       ├── hooks/        # useSwarmStream
│       ├── pages/        # Home, Engagement, FindingDetail, PrintReport, Login, Profile,
│       │                 # OrgSettings, AdminPanel
│       ├── store/        # Zustand engagement + auth stores
│       └── types/        # Shared TypeScript types
├── cli/                  # forge CLI
│   └── forge_cli/
│       ├── commands/     # auth.py · users.py · org_llm.py
│       ├── api.py        # ForgeClient — all HTTP calls to the backend
│       ├── display.py    # Rich tables, panels, event formatters
│       ├── main.py       # Click group + command registration
│       └── stream.py     # WebSocket live event stream
└── docker-compose.yml
```

---

## Screenshots

**Dashboard** — `ps aux`-style engagement list:

![Dashboard](screenshots/dashboard.png)

**Engagement console** — live swarm events with per-type rendering:

![Engagement console](screenshots/engagement-console.png)

**Findings + report** — severity chips and report summary with severity-scaled bars:

![Engagement findings](screenshots/engagement-findings.png)

**Finding detail** — exploit walkthrough, Mermaid attack path, PoC script, live execution verdict:

![Finding](screenshots/finding.png)

**Auth flows** — login, register, profile/API keys, org settings, super admin panel:

![Login](screenshots/auth-login.png)
