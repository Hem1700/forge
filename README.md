# FORGE — Framework for Offensive Reasoning, Generation and Exploitation

A multi-agent autonomous pentesting platform for web applications, local codebases, and Linux hosts — with Strategic Brain + Tactical Swarm architecture, per-finding exploit intelligence, runnable PoC generation, and live WebSocket streaming.

---

## Features

- **Multi-target scanning** — web apps, local codebases, compiled binaries, and Linux hosts over SSH
- **Exploit + PoC generation** — LLM-generated exploit walkthroughs, Mermaid attack paths, and runnable PoC scripts cached per finding
- **OS attack chain discovery** — six parallel SSH agents + `ChainDiscoveryAgent` synthesises multi-step root escalation paths via Neo4j graph traversal
- **Human-in-the-loop gates** — pipeline pause points for analyst review, approvable from the UI or CLI
- **CI/CD integration** — `forge ci scan` exits non-zero on severity breach, with native GitHub commit status and PR comment support

---

## Prerequisites

- Docker + Docker Compose
- Node.js 18+
- Python 3.10+
- An LLM provider API key — Anthropic, OpenAI, AWS Bedrock (IAM role supported), or Azure OpenAI

---

## Quickstart

### 1. Start infrastructure

```bash
docker compose up -d
```

Starts PostgreSQL, Redis, Qdrant, and Neo4j.

### 2. Configure environment

Create `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://forge:forge@localhost:5432/forge
NEO4J_URL=bolt://localhost:17687
NEO4J_USER=neo4j
NEO4J_PASSWORD=forge_password
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379
JWT_SECRET=change-me-in-production
FORGE_SECRETS_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Deployment-level LLM fallback (orgs can override per-org via CLI)
ANTHROPIC_API_KEY=sk-ant-...
```

Create `frontend/.env`:

```env
VITE_API_URL=http://localhost:8080
VITE_WS_URL=ws://localhost:8080
```

### 3. Start the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --port 8080
```

### 4. Start the worker

Engagement pipelines run in a separate process. The API enqueues jobs; the worker executes them and fans events out via Redis pub/sub.

```bash
cd backend && source .venv/bin/activate
arq app.worker.WorkerSettings
```

**The pipeline will not run without this process.**

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev -- --port 5174
```

Open `http://localhost:5174`.

---

## Running a Scan

### Web UI

1. Open `http://localhost:5174` → **+ NEW** → fill in target → **▶ CREATE** → **▶ LAUNCH**
2. Events stream live in the Swarm Console and replay after page refresh
3. Approve human gates when the amber banner appears
4. Click any finding row → **Generate Exploit** / **Generate PoC** / **Execute Against Target**
5. **PDF ↓** in the engagement header downloads the full report

### CLI

Install:

```bash
cd cli && pip install -e .
```

Register and scan:

```bash
# First-time setup
forge register --email you@example.com --password changeme --org-name "My Org"
forge org llm key set anthropic
forge org llm preset balanced

# Web app
forge run https://your-target.com

# Local codebase (auto-detected)
forge run /path/to/project

# View findings, generate PoC, export report
forge findings <engagement-id> --severity critical
forge poc <finding-id>
forge report <engagement-id> --output report.md
```

Running `forge` with no arguments opens an interactive Metasploit-style shell with auto-completion, history, and live backend stats:

```
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

  Framework for Offensive Reasoning, Generation & Exploitation  v1.0

    + ──= 12 engagement(s)  ·  87 finding(s) =──
    + ──= web  ·  local_codebase  ·  binary  ·  os  targets =──
    + ──= backend: online  http://localhost:8080 =──

  Type help for commands  ·  help <cmd> for details  ·  exit to quit

forge> run /path/to/raven
╭──────────── FORGE — Starting Engagement ─────────────╮
│ Target: 📁 /path/to/raven                            │
│ Type:   local_codebase                               │
╰──────────────────────────────────────────────────────╯
Engagement ID: c238eb1a-00fb-413c-9716-e117876fa6e7
✓ Pipeline started

Live event stream (Ctrl+C to detach)
✓ Stream connected

 22:26:10  ▶ AGENT   codebase_modeling  ·  /path/to/raven
 22:26:10  ● PROG    codebase_modeling.walk  ·  walking /path/to/raven
 22:26:45  ✦ CONCL   SQL injection confirmed in auth middleware  (95%)
╭────────── 🔍 FINDING ──────────────────────────────╮
│ [CRITICAL] SQL Injection                            │
│   Location:    src/auth/middleware.py:42            │
│   Confidence:  70%                                  │
╰─────────────────────────────────────────────────────╯
 22:27:01  ⚖ JUDGE   real finding  (92%)  · Direct string interpolation
 22:27:30  ✓ DONE    codebase_modeling  (3 findings, 7 surfaces)
╭────────── ✓ CAMPAIGN COMPLETE ─────────────────────╮
│ ✓ Engagement finished                               │
╰─────────────────────────────────────────────────────╯

╭───────────── ▶ NEXT STEPS ─────────────────────────╮
│  View findings                                      │
│    forge findings c238eb1a-...                      │
│    forge findings c238eb1a-... --severity critical  │
│                                                     │
│  Per-finding actions   (sample uses top finding)    │
│    forge exploit <top-fid>                          │
│    forge poc <top-fid>                              │
│    forge exploit-script <top-fid>                   │
│    forge execute <top-fid>                          │
│                                                     │
│  Reports                                            │
│    forge report c238eb1a-... --output report.md     │
│    forge report c238eb1a-... --pdf                  │
╰─────────────────────────────────────────────────────╯
```

### OS Scan (Linux host over SSH)

```bash
# Key-based auth (recommended)
forge os-target 10.0.0.1 -u ubuntu --auth-type key --key-material ~/.ssh/id_rsa

# Password auth
forge os-target 10.0.0.5 -u ubuntu --auth-type password --key-material s3cr3t

# After the pipeline finishes
forge findings <id> --severity critical   # attack chains are typically CRITICAL
forge report <id> --output os-report.md
```

The pipeline runs `OSModeler` (agentless SSH fingerprint collection) followed by five parallel OS agents, then `ChainDiscoveryAgent` to synthesise multi-step attack chains.

---

## TrackedLLM

Every LLM call in FORGE is wrapped by `TrackedLLM`, which applies five production-hardening layers in sequence: **budget enforcement** (per-org monthly spend cap, HTTP 402 on breach), **rate limiting** (per-provider TPM/RPM sliding window in Redis, HTTP 429 with `Retry-After`), **tier-based model routing** (20 task types mapped to LIGHT/STANDARD/HEAVY, auto-selecting Haiku/Sonnet/Opus without manual config), **context compression** (LLM-assisted summarisation when context exceeds 70% of model limit), and **prompt caching** (Redis response cache + Anthropic native `cache_control`).

Configure per-org credentials, presets, and per-task overrides with `forge org llm`.

→ Full architecture and system design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Running Tests

```bash
cd backend
pytest -v
```

Requires all Docker services running (postgres, redis, qdrant, neo4j).

---

## License

MIT — see [LICENSE](LICENSE).
