# FORGE — Framework for Offensive Reasoning, Generation and Exploitation

A multi-agent autonomous pentesting platform. FORGE supports web applications, local codebases, and CLI tools — with a Strategic Brain + Tactical Swarm architecture, human-in-the-loop gates, and live WebSocket streaming.

---

## Architecture

- **Strategic Brain** — semantic app modeler, codebase modeler, campaign planner, evasion strategist, memory engine (LangChain + Claude)
- **Tactical Swarm** — autonomous agents (recon, probe, evasion, code analyzer, dependency scanner, fuzzer, deep exploit) coordinated by an auction-based scheduler
- **Adversarial Validator** — challenger, context filter, severity scorer, confidence threshold gate
- **Knowledge Base** — Qdrant vector store + Neo4j graph store for cross-engagement learning
- **REST API + WebSocket** — FastAPI backend with live swarm event streaming
- **React Frontend** — real-time engagement dashboard with human gate UI

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

## Running a Pentest

### Via the UI

1. Open `http://localhost:5174`
2. Click **+ New Engagement**
3. Select your target type and fill in the details (see below)
4. Click **Create Engagement**
5. Click **▶ Start Pentest** on the card
6. Click into the engagement to open the live **Swarm Monitor**
7. Approve or reject **Human Gates** when prompted
8. View findings in the **Findings Panel** and export via **Report Viewer**

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
| `DELETE` | `/api/v1/engagements/{id}` | Delete engagement |
| `POST` | `/api/v1/engagements/{id}/start` | Launch the full pipeline |
| `POST` | `/api/v1/gates/{id}/decide` | Approve or reject a human gate |
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

59 tests covering models, APIs, brain components, swarm agents, validator, and multi-target pipeline.

---

## Project Structure

```
FORGE/
├── backend/
│   ├── app/
│   │   ├── api/          # REST endpoints (engagements, gates, knowledge, system, start)
│   │   ├── brain/        # SemanticModeler, CodebaseModeler, CampaignPlanner, MemoryEngine
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
│       ├── api/          # Typed API clients
│       ├── components/   # EngagementDashboard, SwarmMonitor, HumanGate, FindingsPanel, ReportViewer
│       ├── hooks/        # useSwarmStream
│       ├── pages/        # Home, Engagement
│       ├── store/        # Zustand engagement store
│       └── types/        # Shared TypeScript types
└── docker-compose.yml
```
