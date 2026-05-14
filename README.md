# FORGE — Framework for Offensive Reasoning, Generation and Exploitation

A multi-agent autonomous pentesting platform. FORGE supports web applications, local codebases, and CLI tools — with a Strategic Brain + Tactical Swarm architecture, per-finding exploit intelligence, runnable PoC script generation, human-in-the-loop gates, and live WebSocket streaming.

---

## Architecture

- **Auth Layer** — JWT + API key dual authentication, 4-tier RBAC (Viewer / Analyst / Admin / Super-Admin), dependency-injection guards on every route
- **Strategic Brain** — semantic app modeler, codebase modeler, campaign planner, evasion strategist, memory engine (LangChain + Claude)
- **Exploit Engine** — on-demand LLM-generated exploit walkthroughs, Mermaid attack path diagrams, impact analysis, and difficulty scoring per finding
- **PoC Engine** — on-demand runnable exploit script generation (Python or bash, auto-selected by vuln class), Mermaid sequence diagrams showing the attack flow, cached per finding
- **Tactical Swarm** — autonomous agents (recon, probe, evasion, code analyzer, dependency scanner, fuzzer, deep exploit) coordinated by an auction-based scheduler
- **Adversarial Validator** — challenger, context filter, severity scorer, confidence threshold gate
- **Knowledge Base** — Qdrant vector store + Neo4j graph store for cross-engagement learning
- **REST API + WebSocket** — FastAPI backend with live swarm event streaming, events persisted for refresh-safe replay
- **Job Queue + Worker** — engagement pipelines run on an Arq worker process backed by Redis; the API enqueues, the worker executes, and live events fan out via Redis pub/sub so any connected WebSocket client receives them regardless of which API replica it's attached to. The API detects crashed workers on startup and aborts orphaned engagements automatically.
- **React Frontend** — terminal/hacker aesthetic (pure black, cyan accent, monospace), `ps aux`-style engagement dashboard, console-first engagement page with a live swarm log that rehydrates on refresh, per-finding detail pages, attack path + sequence diagrams, PoC viewer with copy/download, PDF report export, human gate UI, login/profile/org-settings/admin panel

---

## Screenshots

**Dashboard** — `ps aux`-style engagement list with launch/view/delete per row:

![Dashboard](docs/screenshots/dashboard.png)

**Engagement page (console)** — live swarm console with per-type event rendering, compact status strip, and start of the findings table:

![Engagement console](docs/screenshots/engagement-console.png)

**Engagement page (findings + report)** — full findings table with severity chips and the report summary with severity-scaled bars:

![Engagement findings](docs/screenshots/engagement-findings.png)

**Finding detail** — description + evidence, LLM-generated exploit walkthrough with Mermaid attack path, runnable PoC script with sequence diagram, and live exploit execution with verdict override:

![Finding](docs/screenshots/finding.png)

---

## Prerequisites

- Docker + Docker Compose
- Node.js 18+
- Python 3.10+
- An Anthropic API key (for LLM-powered analysis)

---

## Getting Started

### 1. Start infrastructure

```bash
docker compose up -d
```

Starts PostgreSQL, Redis, Qdrant, and Neo4j.

### 2. Configure environment

Create `backend/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://forge:forge@localhost:5432/forge
NEO4J_URL=bolt://localhost:17687
NEO4J_USER=neo4j
NEO4J_PASSWORD=forge_password
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379
JWT_SECRET=change-me-in-production
```

Create `frontend/.env`:

```env
VITE_API_URL=http://localhost:8080
VITE_WS_URL=ws://localhost:8080
```

> Neither `.env` file is committed to git.

### 3. Run migrations and start the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --port 8080
```

Backend runs at `http://localhost:8080`. Interactive API docs at `http://localhost:8080/docs`.

### 4. Start the worker

Engagement pipelines run in a separate worker process so they survive uvicorn restarts and so the API can scale horizontally. The worker pulls jobs off Redis and publishes live events back through Redis pub/sub — connected WebSocket clients on any API replica receive them.

```bash
cd backend
source .venv/bin/activate
arq app.worker.WorkerSettings
```

Or `make worker` from the repo root. **The pipeline will not run without this process** — `POST /engagements/{id}/start` enqueues a job, the worker picks it up.

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev -- --port 5174
```

Frontend runs at `http://localhost:5174`.

---

## Authentication

FORGE requires authentication on all API endpoints. On first launch, register the first account — it automatically becomes `super_admin`:

```bash
# Register (first account = super_admin, subsequent = viewer)
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "changeme"}'

# Login and get a JWT
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "changeme"}'
# → {"access_token": "eyJ...", "token_type": "bearer"}
```

Pass the token on every request: `Authorization: Bearer <token>`.

Alternatively, create an API key (`POST /api/v1/auth/api-keys`) and pass it as a Bearer token — FORGE tries JWT first, then falls back to SHA256-hashed API key lookup.

### Role system

| Role | What they can do |
|------|-----------------|
| `viewer` | Read engagements, findings, events |
| `analyst` | Viewer + create/start engagements, triage, generate exploits/PoC/report |
| `admin` | Analyst + manage org users and roles, delete engagements |
| `super_admin` | Admin + cross-org user management and provisioning |

---

## CLI (forge)

The `forge` command-line tool lets you run pentests, stream live events, and export results — no browser required.

### Installation

```bash
cd cli
pip install -e .
```

Verify:

```bash
forge --help
```

### Configuration

Save your API endpoint and key once — all commands pick it up automatically:

```bash
forge configure --api-url http://localhost:8080 --api-key <your-api-key>
```

Config is written to `~/.forge/config.json`. You can also set `FORGE_API_URL` and `FORGE_API_KEY` environment variables to override it per-session.

### Commands

#### `forge configure` — save API endpoint and key

```bash
forge configure --api-url http://localhost:8080 --api-key forge_...
```

Writes to `~/.forge/config.json`. Run this once after creating an API key in the UI or via `POST /api/v1/auth/api-keys`. All other commands use these values automatically.

#### `forge run <target>` — start a pentest

Target type is auto-detected. Pass a URL for web apps, or a filesystem path for local codebases.

```bash
# Web application
forge run https://example.com

# Web with scope
forge run https://example.com --scope /api --scope /admin --out-of-scope /static

# Local codebase (auto-detected from path)
forge run /Users/you/Desktop/myproject

# Binary
forge run /usr/bin/target-binary --type binary

# Start and exit immediately (don't stream events)
forge run https://example.com --no-stream
```

Live swarm events stream to the terminal. Press `Ctrl+C` to detach — the pipeline keeps running in the background.

#### `forge list` — list all engagements

```bash
forge list
```

#### `forge status <id>` — engagement details

```bash
forge status <engagement-id>

# Stream live events for a running engagement
forge status <engagement-id> --watch
```

#### `forge findings <id>` — view findings

```bash
# Severity summary + findings table
forge findings <engagement-id>

# Filter by severity
forge findings <engagement-id> --severity critical
forge findings <engagement-id> --severity high

# Generate and display exploit walkthroughs for all findings
forge findings <engagement-id> --exploit

# Generate and save PoC scripts for all findings
forge findings <engagement-id> --poc

# Output raw JSON
forge findings <engagement-id> --json

# Save to file
forge findings <engagement-id> --output findings.json
```

#### `forge exploit <finding-id>` — exploit walkthrough for a finding

Generate a step-by-step exploit walkthrough, attack path diagram, impact analysis, and difficulty rating for a specific finding. Result is cached — subsequent calls return instantly.

```bash
forge exploit <finding-id>
```

Output includes:
- Numbered exploit steps with PoC code snippets
- ASCII attack path diagram (`Attacker ──[crafted request]──► WebServer`)
- Impact summary and prerequisites
- Difficulty rating (easy / medium / hard)

#### `forge poc <finding-id>` — generate a PoC exploit script

Generate a runnable exploit script for a specific finding. The language is auto-selected based on vulnerability class (Python for SQLi/XSS/SSRF/IDOR/etc., bash for command injection/path traversal). The script is saved to the current directory. Result is cached — subsequent calls return instantly.

```bash
forge poc <finding-id>
```

Output includes:
- Language badge and filename (e.g. `poc_sqli_api_users.py`)
- Syntax-highlighted script with line numbers
- Setup commands (e.g. `pip install requests`)
- Usage notes
- ASCII exploit sequence (`Attacker ──► Server: GET /api/users?id=1' OR '1'='1`)
- Saved file confirmation

#### `forge report <id>` — generate a markdown report

```bash
# Print to terminal
forge report <engagement-id>

# Save to file
forge report <engagement-id> --output report.md
```

When exploit walkthroughs or PoC scripts have been generated, the report includes them automatically under each finding.

#### `forge gate approve/reject <id>` — human gate decisions

```bash
forge gate approve <engagement-id>
forge gate approve <engagement-id> --notes "Reviewed recon output, safe to proceed"

forge gate reject <engagement-id>
forge gate reject <engagement-id> --notes "Out of scope targets detected"
```

#### `forge stats` — platform statistics

```bash
forge stats
```

#### `forge delete <id>` — delete an engagement

```bash
forge delete <engagement-id>

# Skip confirmation prompt
forge delete <engagement-id> --yes
```

### Typical workflow

```bash
# 0. Authenticate once
forge configure --api-url http://localhost:8080 --api-key forge_...

# 1. Start a pentest and stream events live
forge run /Users/you/Desktop/myproject

# 2. (In another terminal, if you detached) check status
forge list
forge status <id>

# 3. Approve a human gate when prompted
forge gate approve <id>

# 4. View findings when complete
forge findings <id>
forge findings <id> --severity critical

# 5. Drill into a specific finding's exploit walkthrough
forge exploit <finding-id>

# 6. Generate a runnable PoC script for a finding (saved to disk)
forge poc <finding-id>

# 7. Export full report (includes exploit walkthroughs + PoC scripts if generated)
forge report <id> --output report.md
```

---

## Running a Pentest

### Via the UI

1. Open `http://localhost:5174`
2. Click **+ NEW** and fill in the target details (see target types below)
3. Click **▶ CREATE ENGAGEMENT**, then **▶ LAUNCH** on the row
4. The engagement page opens with the **Live Swarm Console** as the hero panel — events stream in real time and replay after a page refresh
5. Approve or reject **Human Gates** when the amber banner appears
6. Scan findings in the table below the console — click any row to open its detail page
7. On the finding detail page, click **Generate Exploit** for a walkthrough + attack path, **Generate PoC** for a runnable script + sequence diagram, or **Execute Against Target** to run the weaponized script in a sandboxed Kali container
8. Click **PDF ↓** in the engagement header to download the full report

Click the **×** button on any dashboard row to delete an engagement (findings and events cascade). On startup the backend looks up each `running` engagement's Arq job in Redis — if the job is gone (worker crashed or was killed mid-pipeline) the engagement is aborted immediately with reason `worker crashed before completion`. Engagements stuck at a human gate for over an hour are also swept.

### Via the API

```bash
TOKEN="eyJ..."   # from POST /auth/login

# 1. Create engagement
curl -X POST http://localhost:8080/api/v1/engagements/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_url": "https://example.com", "target_type": "web"}'

# 2. Start pentest
curl -X POST http://localhost:8080/api/v1/engagements/{id}/start \
  -H "Authorization: Bearer $TOKEN"

# 3. Check status
curl http://localhost:8080/api/v1/engagements/{id} \
  -H "Authorization: Bearer $TOKEN"

# 4. Check findings count
curl http://localhost:8080/api/v1/system/stats \
  -H "Authorization: Bearer $TOKEN"
```

---

## Target Types

FORGE supports three target types:

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
- **DependencyScanner** — checks `requirements.txt` / `package.json` / `go.mod` against the [OSV CVE database](https://osv.dev) (no API key needed)
- **Fuzzer** — generates malformed inputs, runs the CLI, detects crashes and hangs

```json
{
  "target_url": "local",
  "target_type": "local_codebase",
  "target_path": "/absolute/path/to/project"
}
```

```bash
# Example: test a local Python project
curl -X POST http://localhost:8080/api/v1/engagements/ \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "local",
    "target_type": "local_codebase",
    "target_path": "/Users/you/Desktop/myproject"
  }'

curl -X POST http://localhost:8080/api/v1/engagements/{id}/start
```

### Binary

Analyzes a compiled binary file (ELF, PE, Mach-O). Same agents as local codebase, focused on the binary file and any surrounding source.

```json
{
  "target_url": "local",
  "target_type": "binary",
  "target_path": "/absolute/path/to/binary"
}
```

---

## API Reference

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
| `POST` | `/api/v1/gates/{id}/decide` | analyst | Approve or reject human gate |
| `GET` | `/api/v1/findings/{id}` | viewer | Get full finding detail (includes `exploit_detail`, `poc_detail`, `exploit_script`, `exploit_execution` if generated) |
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

## Running Tests

```bash
cd backend
# Requires all Docker services running (postgres, redis, qdrant, neo4j)
pytest -v
```

158 tests covering auth flows, RBAC enforcement, API key CRUD, org/super-admin routes, models, APIs, brain components (ExploitEngine, PoCEngine), swarm agents, validator, multi-target pipeline, orphan-engagement sweep, and worker-health endpoint.

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
│   │   │   ├── super_admin.py  # cross-org management (super_admin only)
│   │   │   └── engagements, findings, gates, knowledge, system, start
│   │   ├── brain/        # SemanticModeler, CodebaseModeler, CampaignPlanner, ExploitEngine, PoCEngine, MemoryEngine
│   │   ├── knowledge/    # Vector store (Qdrant) + graph store (Neo4j)
│   │   ├── models/       # SQLAlchemy ORM models (user, api_key, engagement, finding, task, agent, knowledge)
│   │   ├── swarm/        # Agents, scheduler, health monitor, task board
│   │   │   └── agents/   # recon, probe, evasion, code_analyzer, dependency_scanner, fuzzer, deep_exploit
│   │   ├── validator/    # Challenger, context filter, severity scorer
│   │   ├── ws/           # WebSocket stream manager + Redis pub/sub bridge
│   │   ├── queue.py      # ArqRedis pool + enqueue/job_status helpers
│   │   └── worker.py     # Arq WorkerSettings — runs engagement pipelines out-of-process
│   ├── alembic/          # Database migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/          # Typed API clients (auth, engagements, findings, gates)
│       ├── components/   # EngagementDashboard, SwarmMonitor, HumanGate, FindingsPanel, ExploitWalkthrough, AttackPathDiagram, PoCScript, ExploitSequenceDiagram, ReportViewer, ProtectedRoute
│       ├── hooks/        # useSwarmStream
│       ├── pages/        # Home, Engagement, FindingDetail, PrintReport, Login, Profile, OrgSettings, AdminPanel
│       ├── store/        # Zustand engagement + auth stores
│       └── types/        # Shared TypeScript types
├── cli/                  # forge CLI (run, list, status, findings, exploit, poc, report, gate, configure, ...)
└── docker-compose.yml
```
