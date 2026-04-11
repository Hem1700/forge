# FORGE — Framework for Offensive Reasoning, Generation and Exploitation

A multi-agent autonomous pentesting platform. FORGE uses a Strategic Brain + Tactical Swarm architecture to plan, execute, and validate security assessments — with human-in-the-loop gates at key decision points.

---

## Architecture

- **Strategic Brain** — semantic app modeler, campaign planner, evasion strategist, memory engine (LangChain + Claude)
- **Tactical Swarm** — autonomous agents (recon, probe, evasion, logic modeler, deep exploit, child) coordinated by an auction-based scheduler
- **Adversarial Validator** — challenger, context filter, severity scorer, confidence threshold gate
- **Knowledge Base** — Qdrant vector store + Neo4j graph store for cross-engagement learning
- **REST API + WebSocket** — FastAPI backend with live swarm event streaming
- **React Frontend** — real-time engagement dashboard with human gate UI

---

## Prerequisites

- Docker + Docker Compose
- Node.js 18+
- Python 3.10+
- An Anthropic API key

---

## Getting Started

### 1. Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL, Redis, Qdrant, and Neo4j.

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

### 3. Run migrations and start the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`. Interactive API docs at `http://localhost:8000/docs`.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

---

## Running an Engagement

1. Open `http://localhost:5173`
2. Click **+ New Engagement** and enter a target URL (e.g. `https://example.com`)
3. Click into the engagement — it starts in `pending` status
4. Kick off the swarm by patching its status to `running`:

```bash
curl -X PATCH http://localhost:8000/api/v1/engagements/{id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "running"}'
```

5. The **Swarm Monitor** tab shows live events streamed over WebSocket as agents report in
6. When the engagement hits a **Human Gate** (`paused_at_gate`), the UI presents Approve / Reject buttons
7. Findings appear in the **Findings Panel**; use **Export JSON** in the Report Viewer to download results

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/engagements/` | Create engagement |
| `GET` | `/api/v1/engagements/` | List engagements |
| `GET` | `/api/v1/engagements/{id}` | Get engagement |
| `PATCH` | `/api/v1/engagements/{id}/status` | Update status |
| `DELETE` | `/api/v1/engagements/{id}` | Delete engagement |
| `POST` | `/api/v1/gates/{id}/decide` | Approve or reject a gate |
| `GET` | `/api/v1/knowledge/` | List knowledge entries |
| `GET` | `/api/v1/knowledge/attack-class/{class}` | Filter by attack class |
| `GET` | `/api/v1/system/stats` | Engagement / finding / knowledge counts |
| `WS` | `/ws/{engagement_id}` | Live swarm event stream |

Full interactive docs: `http://localhost:8000/docs`

---

## Running Tests

```bash
cd backend
# Requires Docker services running
pytest -v
```

48 tests covering models, APIs, brain components, swarm agents, and the validator.

---

## Project Structure

```
FORGE/
├── backend/
│   ├── app/
│   │   ├── api/          # REST endpoints (engagements, gates, knowledge, system)
│   │   ├── brain/        # Strategic Brain (semantic modeler, campaign planner, etc.)
│   │   ├── knowledge/    # Vector store (Qdrant) + graph store (Neo4j)
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── swarm/        # Agents, scheduler, health monitor, task board
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

---

## What's Next

The swarm agents and brain components are fully implemented but not yet wired to an orchestration entry point. A `POST /api/v1/engagements/{id}/start` route that launches the full pipeline (SemanticModeler → CampaignPlanner → Scheduler → Agents) is the natural next step.
