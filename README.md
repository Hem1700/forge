# FORGE — Framework for Offensive Reasoning, Generation and Exploitation

A multi-agent autonomous pentesting platform. FORGE supports web applications, local codebases, and CLI tools — with a Strategic Brain + Tactical Swarm architecture, per-finding exploit intelligence, runnable PoC script generation, human-in-the-loop gates, and live WebSocket streaming.

---

## Architecture

- **Strategic Brain** — semantic app modeler, codebase modeler, campaign planner, evasion strategist, memory engine (LangChain + Claude)
- **Exploit Engine** — on-demand LLM-generated exploit walkthroughs, Mermaid attack path diagrams, impact analysis, and difficulty scoring per finding
- **PoC Engine** — on-demand runnable exploit script generation (Python or bash, auto-selected by vuln class), Mermaid sequence diagrams showing the attack flow, cached per finding
- **Tactical Swarm** — autonomous agents (recon, probe, evasion, code analyzer, dependency scanner, fuzzer, deep exploit) coordinated by an auction-based scheduler
- **Adversarial Validator** — challenger, context filter, severity scorer, confidence threshold gate
- **Knowledge Base** — Qdrant vector store + Neo4j graph store for cross-engagement learning
- **REST API + WebSocket** — FastAPI backend with live swarm event streaming, events persisted for refresh-safe replay
- **React Frontend** — terminal/hacker aesthetic (pure black, cyan accent, monospace), `ps aux`-style engagement dashboard, console-first engagement page with a live swarm log that rehydrates on refresh, per-finding detail pages, attack path + sequence diagrams, PoC viewer with copy/download, PDF report export, and human gate UI

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

> Use `--reload` during development, but avoid it during active pentests — uvicorn reloads kill running background pipelines.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev -- --port 5174
```

Frontend runs at `http://localhost:5174`.

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

Set the backend URL if it's not on `localhost:8080`:

```bash
export FORGE_API_URL=http://your-server:8080
```

### Commands

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

Click the **×** button on any dashboard row to delete an engagement (findings and events cascade). The backend auto-aborts any engagement stuck in `running`/`paused_at_gate` for over an hour on startup.

### Via the API

```bash
# 1. Create engagement
curl -X POST http://localhost:8080/api/v1/engagements/ \
  -H "Content-Type: application/json" \
  -d '{"target_url": "https://example.com", "target_type": "web"}'

# 2. Start pentest
curl -X POST http://localhost:8080/api/v1/engagements/{id}/start

# 3. Check status
curl http://localhost:8080/api/v1/engagements/{id}

# 4. Check findings count
curl http://localhost:8080/api/v1/system/stats
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

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/engagements/` | Create engagement |
| `GET` | `/api/v1/engagements/` | List engagements |
| `GET` | `/api/v1/engagements/{id}` | Get engagement |
| `PATCH` | `/api/v1/engagements/{id}/status` | Update status (`pending`, `running`, `aborted`) |
| `DELETE` | `/api/v1/engagements/{id}` | Delete engagement (cascades findings, tasks, agents, events, knowledge) |
| `POST` | `/api/v1/engagements/{id}/start` | Launch the full pipeline |
| `GET` | `/api/v1/engagements/{id}/events` | Replay recent swarm events (latest 500) |
| `POST` | `/api/v1/engagements/{id}/report/pdf` | Generate a PDF report |
| `POST` | `/api/v1/gates/{id}/decide` | Approve or reject a human gate |
| `GET` | `/api/v1/findings/{id}` | Get full finding detail (includes `exploit_detail`, `poc_detail`, `exploit_script`, `exploit_execution` if generated) |
| `POST` | `/api/v1/findings/{id}/exploit` | Generate (or return cached) exploit walkthrough |
| `GET` | `/api/v1/findings/{id}/poc` | Get PoC detail for a finding (null if not yet generated) |
| `POST` | `/api/v1/findings/{id}/poc` | Generate (or return cached) PoC script + sequence diagram |
| `POST` | `/api/v1/findings/{id}/exploit-script` | Generate a weaponized exploit script |
| `POST` | `/api/v1/findings/{id}/execute` | Execute the weaponized script against the target (sandboxed) |
| `GET` | `/api/v1/knowledge/` | List knowledge base entries |
| `GET` | `/api/v1/knowledge/attack-class/{class}` | Filter knowledge by attack class |
| `GET` | `/api/v1/system/stats` | Engagement / finding / knowledge counts |
| `WS` | `/ws/{engagement_id}` | Live swarm event stream |

Full interactive docs: `http://localhost:8080/docs`

---

## Running Tests

```bash
cd backend
# Requires Docker services running
pytest -v
```

78 tests covering models, APIs, brain components (ExploitEngine, PoCEngine), swarm agents, validator, and multi-target pipeline.

---

## Project Structure

```
FORGE/
├── backend/
│   ├── app/
│   │   ├── api/          # REST endpoints (engagements, findings, gates, knowledge, system, start)
│   │   ├── brain/        # SemanticModeler, CodebaseModeler, CampaignPlanner, ExploitEngine, PoCEngine, MemoryEngine
│   │   ├── knowledge/    # Vector store (Qdrant) + graph store (Neo4j)
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── swarm/        # Agents, scheduler, health monitor, task board
│   │   │   └── agents/   # recon, probe, evasion, code_analyzer, dependency_scanner, fuzzer, deep_exploit
│   │   ├── validator/    # Challenger, context filter, severity scorer
│   │   └── ws/           # WebSocket stream manager
│   ├── alembic/          # Database migrations
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/          # Typed API clients (engagements, findings, gates)
│       ├── components/   # EngagementDashboard, SwarmMonitor, HumanGate, FindingsPanel, ExploitWalkthrough, AttackPathDiagram, PoCScript, ExploitSequenceDiagram, ReportViewer
│       ├── hooks/        # useSwarmStream
│       ├── pages/        # Home, Engagement, FindingDetail, PrintReport
│       ├── store/        # Zustand engagement store
│       └── types/        # Shared TypeScript types
└── docker-compose.yml
```
