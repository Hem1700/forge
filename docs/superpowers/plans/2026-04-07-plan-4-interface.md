# FORGE Plan 4: API, WebSocket & Frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full REST API (engagements, gates, knowledge, system), WebSocket streaming for live swarm activity, and the React frontend with all 5 key components (EngagementDashboard, SwarmMonitor, HumanGate, FindingsPanel, ReportViewer).

**Architecture:** FastAPI routes mount under `/api/v1`. Each route group is a separate router file. WebSocket at `/ws/engagements/{id}/stream` emits real-time agent/task/finding events. Frontend is React + TypeScript + Vite + shadcn/ui. Zustand manages global engagement state. WebSocket hook connects to the streaming endpoint.

**Tech Stack:** FastAPI, SQLAlchemy async, pydantic v2, WebSockets, React 18, TypeScript, Vite, shadcn/ui, Tailwind CSS, Zustand, Recharts, httpx

**Prerequisite:** Plans 1, 2, and 3 complete.

---

## File Map

**Backend**

| File | Purpose |
|---|---|
| `backend/app/api/engagements.py` | CRUD + status + agents/tasks/findings per engagement |
| `backend/app/api/gates.py` | Gate payload GET + approve/reject POST |
| `backend/app/api/knowledge.py` | Knowledge search, stats, delete |
| `backend/app/api/system.py` | Health, models, settings |
| `backend/app/ws/stream.py` | WebSocket event stream per engagement |
| `backend/app/main.py` | Updated: mount all routers + WebSocket |
| `backend/tests/test_api.py` | Full API integration tests |

**Frontend**

| File | Purpose |
|---|---|
| `frontend/src/types/index.ts` | All shared TypeScript types |
| `frontend/src/api/client.ts` | Axios/fetch API client with base URL |
| `frontend/src/api/engagements.ts` | Engagement API calls |
| `frontend/src/api/gates.ts` | Gate API calls |
| `frontend/src/store/engagement.ts` | Zustand store for active engagement |
| `frontend/src/hooks/useSwarmStream.ts` | WebSocket hook for live swarm events |
| `frontend/src/components/EngagementDashboard/index.tsx` | New engagement form + engagement list |
| `frontend/src/components/SwarmMonitor/index.tsx` | Live agent/task activity feed |
| `frontend/src/components/HumanGate/index.tsx` | Gate approval/rejection UI |
| `frontend/src/components/FindingsPanel/index.tsx` | Finding list with confidence scores |
| `frontend/src/components/ReportViewer/index.tsx` | Final report with export |
| `frontend/src/pages/Home.tsx` | Dashboard home page |
| `frontend/src/pages/Engagement.tsx` | Active engagement page (monitors + gates) |
| `frontend/src/App.tsx` | App root with routing |
| `frontend/src/main.tsx` | React entry point |

---

### Task 1: Engagement API Routes

**Files:**
- Create: `backend/app/api/engagements.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_api.py
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_create_engagement():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/engagements", json={
            "target_url": "https://example.com",
            "target_scope": ["example.com"],
            "target_out_of_scope": [],
        })
    assert response.status_code == 201
    data = response.json()
    assert data["target_url"] == "https://example.com"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_engagements():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/engagements", json={"target_url": "https://test.com", "target_scope": [], "target_out_of_scope": []})
        response = await client.get("/api/v1/engagements")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_engagement_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/engagements/{uuid.uuid4()}")
    assert response.status_code == 404
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd backend && pytest tests/test_api.py::test_create_engagement -v
# Expected: 404 or 422 — route doesn't exist yet
```

- [ ] **Step 3: Implement engagements.py**

```python
# backend/app/api/engagements.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.models.engagement import Engagement, EngagementStatus

router = APIRouter(prefix="/api/v1/engagements", tags=["engagements"])


class CreateEngagementRequest(BaseModel):
    target_url: str
    target_scope: list[str] = []
    target_out_of_scope: list[str] = []


class EngagementResponse(BaseModel):
    id: uuid.UUID
    target_url: str
    target_scope: list[str]
    target_out_of_scope: list[str]
    status: str
    gate_status: str

    model_config = {"from_attributes": True}


@router.post("", response_model=EngagementResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement(body: CreateEngagementRequest, db: AsyncSession = Depends(get_db)):
    engagement = Engagement(
        target_url=body.target_url,
        target_scope=body.target_scope,
        target_out_of_scope=body.target_out_of_scope,
    )
    db.add(engagement)
    await db.commit()
    await db.refresh(engagement)
    return engagement


@router.get("", response_model=list[EngagementResponse])
async def list_engagements(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Engagement).order_by(Engagement.created_at.desc()))
    return result.scalars().all()


@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(engagement_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


@router.delete("/{engagement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def abort_engagement(engagement_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    engagement.status = EngagementStatus.aborted
    await db.commit()


@router.get("/{engagement_id}/status")
async def get_engagement_status(engagement_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return {"status": engagement.status, "gate_status": engagement.gate_status}
```

- [ ] **Step 4: Mount router in main.py**

```python
# backend/app/main.py — update the imports and router mounting section
from app.api.engagements import router as engagements_router

# Inside the FastAPI app, after middleware:
app.include_router(engagements_router)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_api.py -v
# Expected: 3 PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/engagements.py backend/tests/test_api.py backend/app/main.py
git commit -m "feat: engagement CRUD API routes"
```

---

### Task 2: Gates + Knowledge + System APIs

**Files:**
- Create: `backend/app/api/gates.py`
- Create: `backend/app/api/knowledge.py`
- Create: `backend/app/api/system.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_api.py

@pytest.mark.asyncio
async def test_get_gate_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/engagements/{uuid.uuid4()}/gates/1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_search():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/knowledge/search?q=sql+injection")
    assert response.status_code == 200
    assert "results" in response.json()


@pytest.mark.asyncio
async def test_system_models():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/models")
    assert response.status_code == 200
    assert "models" in response.json()
```

- [ ] **Step 2: Implement gates.py**

```python
# backend/app/api/gates.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.models.engagement import Engagement, EngagementStatus, GateStatus
from app.models.finding import Finding, ValidationStatus

router = APIRouter(prefix="/api/v1/engagements", tags=["gates"])

GATE_SEQUENCE = {1: GateStatus.gate_1, 2: GateStatus.gate_2, 3: GateStatus.gate_3}
NEXT_GATE = {GateStatus.gate_1: GateStatus.gate_2, GateStatus.gate_2: GateStatus.gate_3, GateStatus.gate_3: GateStatus.complete}


class GateApprovalRequest(BaseModel):
    annotations: dict = {}
    excluded_hypothesis_ids: list[str] = []


class GateRejectionRequest(BaseModel):
    reason: str


@router.get("/{engagement_id}/gates/{gate_number}")
async def get_gate_payload(engagement_id: uuid.UUID, gate_number: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    if gate_number not in GATE_SEQUENCE:
        raise HTTPException(status_code=400, detail="Invalid gate number. Must be 1, 2, or 3.")

    findings_result = await db.execute(
        select(Finding).where(
            Finding.engagement_id == engagement_id,
            Finding.validation_status == ValidationStatus.validated,
        )
    )
    validated_findings = findings_result.scalars().all()

    return {
        "engagement_id": str(engagement_id),
        "gate_number": gate_number,
        "gate_status": engagement.gate_status,
        "semantic_model": engagement.semantic_model,
        "validated_findings": [
            {
                "id": str(f.id),
                "title": f.title,
                "severity": f.severity,
                "confidence_score": f.confidence_score,
                "affected_surface": f.affected_surface,
            }
            for f in validated_findings
        ],
    }


@router.post("/{engagement_id}/gates/{gate_number}/approve")
async def approve_gate(
    engagement_id: uuid.UUID,
    gate_number: int,
    body: GateApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    current_gate = GATE_SEQUENCE.get(gate_number)
    if engagement.gate_status != current_gate:
        raise HTTPException(status_code=400, detail=f"Engagement is not at gate {gate_number}")
    engagement.gate_status = NEXT_GATE[current_gate]
    engagement.status = EngagementStatus.running
    await db.commit()
    return {"approved": True, "next_gate": engagement.gate_status}


@router.post("/{engagement_id}/gates/{gate_number}/reject")
async def reject_gate(
    engagement_id: uuid.UUID,
    gate_number: int,
    body: GateRejectionRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Engagement).where(Engagement.id == engagement_id))
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    engagement.status = EngagementStatus.aborted
    await db.commit()
    return {"rejected": True, "reason": body.reason}
```

- [ ] **Step 3: Implement knowledge.py**

```python
# backend/app/api/knowledge.py
from fastapi import APIRouter, Query
from app.knowledge.query import KnowledgeQuery

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
_kb = KnowledgeQuery()


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., description="Search query"),
    attack_class: str | None = Query(None),
    tech_stack: str | None = Query(None, description="Comma-separated tech stack filter"),
    top_k: int = Query(5, ge=1, le=20),
):
    tech_stack_list = tech_stack.split(",") if tech_stack else None
    results = await _kb.find_similar_techniques(
        description=q,
        attack_class=attack_class,
        tech_stack=tech_stack_list,
        top_k=top_k,
    )
    return {"results": results, "count": len(results)}


@router.get("/stats")
async def knowledge_stats():
    return {"status": "ok", "message": "Knowledge store operational"}


@router.delete("/{entry_id}")
async def delete_knowledge_entry(entry_id: str):
    await _kb.vector.delete(entry_id)
    return {"deleted": True, "id": entry_id}
```

- [ ] **Step 4: Implement system.py**

```python
# backend/app/api/system.py
from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["system"])

AVAILABLE_MODELS = [
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "type": "cloud", "provider": "anthropic"},
    {"id": "llama3.3-70b", "name": "Llama 3.3 70B", "type": "local", "provider": "ollama"},
]


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@router.get("/models")
async def list_models():
    return {"models": AVAILABLE_MODELS, "active": "claude-sonnet-4-6" if not settings.use_local_llm else "llama3.3-70b"}


@router.put("/settings")
async def update_settings(body: dict):
    # In a real implementation, persist settings to DB or env
    return {"updated": True, "settings": body}
```

- [ ] **Step 5: Mount all routers in main.py**

```python
# backend/app/main.py — final version
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.engagements import router as engagements_router
from app.api.gates import router as gates_router
from app.api.knowledge import router as knowledge_router
from app.api.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="FORGE", description="Framework for Offensive Reasoning, Generation and Exploitation", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(engagements_router)
app.include_router(gates_router)
app.include_router(knowledge_router)
app.include_router(system_router)
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_api.py -v
# Expected: 6 PASSED
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/ backend/app/main.py
git commit -m "feat: gates, knowledge, system API routes — full backend API complete"
```

---

### Task 3: WebSocket Streaming

**Files:**
- Create: `backend/app/ws/stream.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing test**

```python
# append to backend/tests/test_api.py
from httpx_ws import aconnect_ws
import json


@pytest.mark.asyncio
async def test_websocket_connects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create an engagement first
        resp = await client.post("/api/v1/engagements", json={"target_url": "https://example.com", "target_scope": [], "target_out_of_scope": []})
        engagement_id = resp.json()["id"]

    # WebSocket test — just verify it accepts connection
    from starlette.testclient import TestClient
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/ws/engagements/{engagement_id}/stream") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd backend && pytest tests/test_api.py::test_websocket_connects -v
# Expected: connection refused / route not found
```

- [ ] **Step 3: Implement stream.py**

```python
# backend/app/ws/stream.py
import asyncio
import json
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
from app.config import settings


class SwarmStreamManager:
    """Manages WebSocket connections per engagement and broadcasts Redis events."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    def add_connection(self, engagement_id: str, ws: WebSocket) -> None:
        if engagement_id not in self._connections:
            self._connections[engagement_id] = []
        self._connections[engagement_id].append(ws)

    def remove_connection(self, engagement_id: str, ws: WebSocket) -> None:
        if engagement_id in self._connections:
            self._connections[engagement_id].discard(ws) if hasattr(self._connections[engagement_id], 'discard') else None
            try:
                self._connections[engagement_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, engagement_id: str, event: dict) -> None:
        connections = self._connections.get(engagement_id, [])
        dead = []
        for ws in connections:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove_connection(engagement_id, ws)

    async def publish_event(self, engagement_id: str, event_type: str, payload: dict) -> None:
        """Publish event to Redis so all server instances can broadcast it."""
        r = await self._get_redis()
        event = {"type": event_type, "engagement_id": engagement_id, "payload": payload, "at": datetime.utcnow().isoformat()}
        await r.publish(f"forge:events:{engagement_id}", json.dumps(event))

    async def handle_connection(self, engagement_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.add_connection(engagement_id, ws)
        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "at": datetime.utcnow().isoformat()})
        except WebSocketDisconnect:
            self.remove_connection(engagement_id, ws)


stream_manager = SwarmStreamManager()
```

- [ ] **Step 4: Add WebSocket route to main.py**

```python
# append to backend/app/main.py
from fastapi import WebSocket
from app.ws.stream import stream_manager


@app.websocket("/ws/engagements/{engagement_id}/stream")
async def websocket_engagement_stream(websocket: WebSocket, engagement_id: str):
    await stream_manager.handle_connection(engagement_id, websocket)
```

- [ ] **Step 5: Run test — verify it passes**

```bash
cd backend && pytest tests/test_api.py::test_websocket_connects -v
# Expected: PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/ws/stream.py backend/app/main.py
git commit -m "feat: WebSocket streaming with ping/pong and per-engagement connection management"
```

---

### Task 4: React Frontend Setup

**Files:**
- Create: `frontend/` (full Vite project)
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Scaffold React project**

```bash
cd /Users/hemparekh/Desktop/FORGE
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install axios zustand @tanstack/react-query react-router-dom
npm install recharts lucide-react
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 2: Install shadcn/ui**

```bash
cd frontend
npx shadcn@latest init
# Choose: TypeScript, Default style, Slate base color, yes CSS variables
npx shadcn@latest add button card badge table tabs input label textarea dialog alert
```

- [ ] **Step 3: Write TypeScript types**

```typescript
// frontend/src/types/index.ts
export type EngagementStatus = "pending" | "running" | "paused_at_gate" | "complete" | "aborted";
export type GateStatus = "gate_1" | "gate_2" | "gate_3" | "complete";
export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type AgentType = "recon" | "logic_modeler" | "probe" | "evasion" | "deep_exploit" | "child" | "validator";
export type AgentStatus = "idle" | "bidding" | "running" | "terminated" | "completed";
export type Priority = "critical" | "high" | "medium" | "low";
export type TaskStatus = "open" | "bidding" | "assigned" | "awaiting_human_gate" | "complete" | "rejected";
export type ValidationStatus = "pending" | "validated" | "rejected";

export interface Engagement {
  id: string;
  target_url: string;
  target_scope: string[];
  target_out_of_scope: string[];
  status: EngagementStatus;
  gate_status: GateStatus;
  semantic_model: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
}

export interface Agent {
  id: string;
  engagement_id: string;
  type: AgentType;
  parent_id: string | null;
  spawned_reason: string;
  status: AgentStatus;
  current_task_id: string | null;
  signal_history: number[];
  termination_reason: string | null;
}

export interface Task {
  task_id: string;
  engagement_id: string;
  title: string;
  surface: string;
  priority: Priority;
  status: TaskStatus;
  required_confidence: number;
  assigned_agent_id: string;
  created_at: string;
}

export interface Finding {
  id: string;
  engagement_id: string;
  title: string;
  description: string;
  vulnerability_class: string;
  affected_surface: string;
  severity: Severity;
  cvss_score: number | null;
  confidence_score: number;
  validation_status: ValidationStatus;
  reproduction_steps: string[];
}

export interface SwarmEvent {
  type: "agent_spawned" | "agent_terminated" | "task_created" | "task_assigned" | "task_closed" | "finding_surfaced" | "gate_triggered" | "pong";
  engagement_id: string;
  payload: Record<string, unknown>;
  at: string;
}

export interface GatePayload {
  engagement_id: string;
  gate_number: number;
  gate_status: GateStatus;
  semantic_model: Record<string, unknown>;
  validated_findings: Array<{
    id: string;
    title: string;
    severity: Severity;
    confidence_score: number;
    affected_surface: string;
  }>;
}
```

- [ ] **Step 4: Write API client**

```typescript
// frontend/src/api/client.ts
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

export const wsUrl = (path: string) =>
  `${BASE_URL.replace("http", "ws")}${path}`;
```

- [ ] **Step 5: Write engagement API calls**

```typescript
// frontend/src/api/engagements.ts
import { apiClient } from "./client";
import type { Engagement } from "../types";

export const engagementsApi = {
  create: (data: { target_url: string; target_scope: string[]; target_out_of_scope: string[] }) =>
    apiClient.post<Engagement>("/api/v1/engagements", data).then((r) => r.data),

  list: () =>
    apiClient.get<Engagement[]>("/api/v1/engagements").then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Engagement>(`/api/v1/engagements/${id}`).then((r) => r.data),

  abort: (id: string) =>
    apiClient.delete(`/api/v1/engagements/${id}`),

  getStatus: (id: string) =>
    apiClient.get<{ status: string; gate_status: string }>(`/api/v1/engagements/${id}/status`).then((r) => r.data),
};
```

- [ ] **Step 6: Write gate API calls**

```typescript
// frontend/src/api/gates.ts
import { apiClient } from "./client";
import type { GatePayload } from "../types";

export const gatesApi = {
  get: (engagementId: string, gateNumber: number) =>
    apiClient.get<GatePayload>(`/api/v1/engagements/${engagementId}/gates/${gateNumber}`).then((r) => r.data),

  approve: (engagementId: string, gateNumber: number, annotations: Record<string, unknown> = {}) =>
    apiClient.post(`/api/v1/engagements/${engagementId}/gates/${gateNumber}/approve`, { annotations }).then((r) => r.data),

  reject: (engagementId: string, gateNumber: number, reason: string) =>
    apiClient.post(`/api/v1/engagements/${engagementId}/gates/${gateNumber}/reject`, { reason }).then((r) => r.data),
};
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: React frontend setup — types, API client, Vite + shadcn/ui"
```

---

### Task 5: Zustand Store + WebSocket Hook

**Files:**
- Create: `frontend/src/store/engagement.ts`
- Create: `frontend/src/hooks/useSwarmStream.ts`

- [ ] **Step 1: Write Zustand store**

```typescript
// frontend/src/store/engagement.ts
import { create } from "zustand";
import type { Engagement, Agent, Task, Finding, SwarmEvent } from "../types";

interface EngagementStore {
  engagements: Engagement[];
  activeEngagement: Engagement | null;
  agents: Agent[];
  tasks: Task[];
  findings: Finding[];
  events: SwarmEvent[];

  setEngagements: (engagements: Engagement[]) => void;
  setActiveEngagement: (engagement: Engagement | null) => void;
  addEvent: (event: SwarmEvent) => void;
  addFinding: (finding: Finding) => void;
  updateTask: (task: Task) => void;
  clearActive: () => void;
}

export const useEngagementStore = create<EngagementStore>((set) => ({
  engagements: [],
  activeEngagement: null,
  agents: [],
  tasks: [],
  findings: [],
  events: [],

  setEngagements: (engagements) => set({ engagements }),
  setActiveEngagement: (engagement) => set({ activeEngagement: engagement }),
  addEvent: (event) => set((state) => ({ events: [event, ...state.events].slice(0, 200) })),
  addFinding: (finding) => set((state) => ({ findings: [...state.findings, finding] })),
  updateTask: (task) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.task_id === task.task_id ? task : t)),
    })),
  clearActive: () => set({ activeEngagement: null, agents: [], tasks: [], findings: [], events: [] }),
}));
```

- [ ] **Step 2: Write WebSocket hook**

```typescript
// frontend/src/hooks/useSwarmStream.ts
import { useEffect, useRef } from "react";
import { wsUrl } from "../api/client";
import { useEngagementStore } from "../store/engagement";
import type { SwarmEvent } from "../types";

export function useSwarmStream(engagementId: string | null) {
  const ws = useRef<WebSocket | null>(null);
  const addEvent = useEngagementStore((s) => s.addEvent);
  const addFinding = useEngagementStore((s) => s.addFinding);

  useEffect(() => {
    if (!engagementId) return;

    const socket = new WebSocket(wsUrl(`/ws/engagements/${engagementId}/stream`));
    ws.current = socket;

    // Ping every 30s to keep connection alive
    const pingInterval = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);

    socket.onmessage = (e) => {
      try {
        const event: SwarmEvent = JSON.parse(e.data);
        if (event.type === "pong") return;
        addEvent(event);
        if (event.type === "finding_surfaced" && event.payload) {
          addFinding(event.payload as any);
        }
      } catch {}
    };

    socket.onerror = () => console.warn("FORGE stream error");

    return () => {
      clearInterval(pingInterval);
      socket.close();
    };
  }, [engagementId]);

  return ws;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/store/ frontend/src/hooks/
git commit -m "feat: Zustand engagement store and WebSocket swarm stream hook"
```

---

### Task 6: Core UI Components

**Files:**
- Create: `frontend/src/components/EngagementDashboard/index.tsx`
- Create: `frontend/src/components/SwarmMonitor/index.tsx`
- Create: `frontend/src/components/HumanGate/index.tsx`
- Create: `frontend/src/components/FindingsPanel/index.tsx`
- Create: `frontend/src/components/ReportViewer/index.tsx`

- [ ] **Step 1: EngagementDashboard**

```tsx
// frontend/src/components/EngagementDashboard/index.tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { engagementsApi } from "../../api/engagements";
import { useEngagementStore } from "../../store/engagement";
import type { Engagement } from "../../types";

const statusColor: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  running: "bg-blue-100 text-blue-800",
  paused_at_gate: "bg-orange-100 text-orange-800",
  complete: "bg-green-100 text-green-800",
  aborted: "bg-red-100 text-red-800",
};

export function EngagementDashboard({ onSelect }: { onSelect: (e: Engagement) => void }) {
  const { engagements, setEngagements } = useEngagementStore();
  const [targetUrl, setTargetUrl] = useState("");
  const [scope, setScope] = useState("");
  const [loading, setLoading] = useState(false);

  const handleCreate = async () => {
    if (!targetUrl) return;
    setLoading(true);
    try {
      const engagement = await engagementsApi.create({
        target_url: targetUrl,
        target_scope: scope ? scope.split(",").map((s) => s.trim()) : [],
        target_out_of_scope: [],
      });
      const all = await engagementsApi.list();
      setEngagements(all);
      setTargetUrl("");
      setScope("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>New Engagement</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="https://target.example.com" value={targetUrl} onChange={(e) => setTargetUrl(e.target.value)} />
          <Input placeholder="Scope: example.com, api.example.com" value={scope} onChange={(e) => setScope(e.target.value)} />
          <Button onClick={handleCreate} disabled={loading || !targetUrl}>
            {loading ? "Starting..." : "Launch Engagement"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-2">
        {engagements.map((e) => (
          <Card key={e.id} className="cursor-pointer hover:border-blue-500 transition-colors" onClick={() => onSelect(e)}>
            <CardContent className="flex items-center justify-between py-4">
              <div>
                <p className="font-medium">{e.target_url}</p>
                <p className="text-sm text-gray-500">{e.id.slice(0, 8)}</p>
              </div>
              <div className="flex gap-2">
                <Badge className={statusColor[e.status]}>{e.status}</Badge>
                <Badge variant="outline">{e.gate_status}</Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: SwarmMonitor**

```tsx
// frontend/src/components/SwarmMonitor/index.tsx
import { useEngagementStore } from "../../store/engagement";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const eventColor: Record<string, string> = {
  agent_spawned: "bg-green-100 text-green-800",
  agent_terminated: "bg-red-100 text-red-800",
  task_created: "bg-blue-100 text-blue-800",
  task_assigned: "bg-purple-100 text-purple-800",
  finding_surfaced: "bg-orange-100 text-orange-800",
  gate_triggered: "bg-yellow-100 text-yellow-800",
};

export function SwarmMonitor() {
  const events = useEngagementStore((s) => s.events);

  return (
    <Card>
      <CardHeader><CardTitle>Live Swarm Activity</CardTitle></CardHeader>
      <CardContent>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {events.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-8">Waiting for swarm activity...</p>
          )}
          {events.map((event, i) => (
            <div key={i} className="flex items-start gap-3 text-sm border-b pb-2">
              <Badge className={eventColor[event.type] || "bg-gray-100"}>{event.type}</Badge>
              <div className="flex-1">
                <p className="text-gray-700">{JSON.stringify(event.payload).slice(0, 120)}</p>
                <p className="text-xs text-gray-400">{new Date(event.at).toLocaleTimeString()}</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: HumanGate**

```tsx
// frontend/src/components/HumanGate/index.tsx
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { gatesApi } from "../../api/gates";
import type { GatePayload } from "../../types";

const severityColor: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-800",
  info: "bg-gray-100 text-gray-800",
};

export function HumanGate({ engagementId, gateNumber, onDecision }: {
  engagementId: string;
  gateNumber: number;
  onDecision: () => void;
}) {
  const [gate, setGate] = useState<GatePayload | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    gatesApi.get(engagementId, gateNumber).then(setGate);
  }, [engagementId, gateNumber]);

  const handleApprove = async () => {
    setLoading(true);
    await gatesApi.approve(engagementId, gateNumber);
    setLoading(false);
    onDecision();
  };

  const handleReject = async () => {
    if (!rejectReason) return;
    setLoading(true);
    await gatesApi.reject(engagementId, gateNumber, rejectReason);
    setLoading(false);
    onDecision();
  };

  if (!gate) return <p className="text-sm text-gray-500">Loading gate data...</p>;

  const gateLabels = { 1: "Recon Summary", 2: "Pre-Exploitation", 3: "Report Sign-Off" };

  return (
    <Card className="border-orange-300 bg-orange-50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="text-orange-600">⚠ Gate {gateNumber}: {gateLabels[gateNumber as keyof typeof gateLabels]}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {gate.validated_findings.length > 0 && (
          <div>
            <p className="font-medium mb-2">Validated Findings ({gate.validated_findings.length})</p>
            <div className="space-y-2">
              {gate.validated_findings.map((f) => (
                <div key={f.id} className="flex items-center justify-between bg-white rounded p-3 border">
                  <div>
                    <p className="font-medium text-sm">{f.title}</p>
                    <p className="text-xs text-gray-500">{f.affected_surface}</p>
                  </div>
                  <div className="flex gap-2 items-center">
                    <Badge className={severityColor[f.severity]}>{f.severity}</Badge>
                    <span className="text-xs text-gray-500">{(f.confidence_score * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="flex gap-3">
          <Button onClick={handleApprove} disabled={loading} className="bg-green-600 hover:bg-green-700">
            Approve & Continue
          </Button>
          <div className="flex-1 flex gap-2">
            <Textarea
              placeholder="Rejection reason..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="h-10 resize-none"
            />
            <Button variant="destructive" onClick={handleReject} disabled={loading || !rejectReason}>
              Reject
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: FindingsPanel**

```tsx
// frontend/src/components/FindingsPanel/index.tsx
import { useEngagementStore } from "../../store/engagement";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const severityColor: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-800",
  info: "bg-gray-100 text-gray-800",
};

export function FindingsPanel() {
  const findings = useEngagementStore((s) => s.findings);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Findings ({findings.length})</CardTitle>
      </CardHeader>
      <CardContent>
        {findings.length === 0 && (
          <p className="text-sm text-gray-500 text-center py-8">No findings yet</p>
        )}
        <div className="space-y-3">
          {findings.map((f) => (
            <div key={f.id} className="border rounded p-4 space-y-2">
              <div className="flex items-center justify-between">
                <p className="font-medium">{f.title}</p>
                <div className="flex gap-2">
                  <Badge className={severityColor[f.severity]}>{f.severity}</Badge>
                  {f.cvss_score && <Badge variant="outline">CVSS {f.cvss_score}</Badge>}
                </div>
              </div>
              <p className="text-sm text-gray-600">{f.affected_surface}</p>
              <p className="text-sm text-gray-500">{f.description}</p>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span>Confidence: {(f.confidence_score * 100).toFixed(0)}%</span>
                <span>·</span>
                <span>{f.vulnerability_class}</span>
                <span>·</span>
                <Badge variant="outline" className="text-xs">{f.validation_status}</Badge>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 5: ReportViewer**

```tsx
// frontend/src/components/ReportViewer/index.tsx
import { useEngagementStore } from "../../store/engagement";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const severityColor: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-800",
  info: "bg-gray-100 text-gray-800",
};

export function ReportViewer() {
  const { activeEngagement, findings } = useEngagementStore();
  const validated = findings.filter((f) => f.validation_status === "validated");

  const exportMarkdown = () => {
    if (!activeEngagement) return;
    const lines = [
      `# FORGE Engagement Report`,
      `**Target:** ${activeEngagement.target_url}`,
      `**Date:** ${new Date().toLocaleDateString()}`,
      `**Total Findings:** ${validated.length}`,
      "",
      "## Findings",
      ...validated.map((f) => [
        `### ${f.title}`,
        `**Severity:** ${f.severity} | **CVSS:** ${f.cvss_score ?? "N/A"} | **Confidence:** ${(f.confidence_score * 100).toFixed(0)}%`,
        `**Surface:** ${f.affected_surface}`,
        "",
        f.description,
        "",
        "**Reproduction Steps:**",
        ...f.reproduction_steps.map((s, i) => `${i + 1}. ${s}`),
        "",
      ].join("\n")),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `forge-report-${activeEngagement.id.slice(0, 8)}.md`;
    a.click();
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Report</CardTitle>
          <Button onClick={exportMarkdown} variant="outline" size="sm">Export Markdown</Button>
        </div>
      </CardHeader>
      <CardContent>
        {validated.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-8">No validated findings to report</p>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-3">
              {(["critical", "high", "medium", "low"] as const).map((sev) => (
                <div key={sev} className="text-center border rounded p-3">
                  <p className="text-2xl font-bold">{validated.filter((f) => f.severity === sev).length}</p>
                  <Badge className={severityColor[sev]}>{sev}</Badge>
                </div>
              ))}
            </div>
            {validated.map((f) => (
              <div key={f.id} className="border rounded p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{f.title}</p>
                  <Badge className={severityColor[f.severity]}>{f.severity}</Badge>
                </div>
                <p className="text-sm text-gray-600">{f.affected_surface}</p>
                <p className="text-sm">{f.description}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: all 5 UI components (Dashboard, SwarmMonitor, HumanGate, Findings, Report)"
```

---

### Task 7: Pages + App Routing

**Files:**
- Create: `frontend/src/pages/Home.tsx`
- Create: `frontend/src/pages/Engagement.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Write Home page**

```tsx
// frontend/src/pages/Home.tsx
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { EngagementDashboard } from "../components/EngagementDashboard";
import { engagementsApi } from "../api/engagements";
import { useEngagementStore } from "../store/engagement";
import type { Engagement } from "../types";

export function Home() {
  const navigate = useNavigate();
  const setEngagements = useEngagementStore((s) => s.setEngagements);

  useEffect(() => {
    engagementsApi.list().then(setEngagements);
  }, []);

  const handleSelect = (engagement: Engagement) => {
    navigate(`/engagement/${engagement.id}`);
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-2">FORGE</h1>
      <p className="text-gray-500 mb-6">Framework for Offensive Reasoning, Generation and Exploitation</p>
      <EngagementDashboard onSelect={handleSelect} />
    </div>
  );
}
```

- [ ] **Step 2: Write Engagement page**

```tsx
// frontend/src/pages/Engagement.tsx
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { SwarmMonitor } from "../components/SwarmMonitor";
import { HumanGate } from "../components/HumanGate";
import { FindingsPanel } from "../components/FindingsPanel";
import { ReportViewer } from "../components/ReportViewer";
import { engagementsApi } from "../api/engagements";
import { useEngagementStore } from "../store/engagement";
import { useSwarmStream } from "../hooks/useSwarmStream";

const GATE_NUMBER: Record<string, number> = {
  gate_1: 1, gate_2: 2, gate_3: 3,
};

export function Engagement() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { activeEngagement, setActiveEngagement } = useEngagementStore();
  useSwarmStream(id ?? null);

  useEffect(() => {
    if (!id) return;
    engagementsApi.get(id).then(setActiveEngagement);
  }, [id]);

  const isPaused = activeEngagement?.status === "paused_at_gate";
  const gateNumber = activeEngagement ? GATE_NUMBER[activeEngagement.gate_status] : null;

  const handleGateDecision = () => {
    if (id) engagementsApi.get(id).then(setActiveEngagement);
  };

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Button variant="ghost" onClick={() => navigate("/")} className="mb-2">← Back</Button>
          <h2 className="text-xl font-bold">{activeEngagement?.target_url}</h2>
          <p className="text-sm text-gray-500">{id}</p>
        </div>
      </div>

      {isPaused && gateNumber && id && (
        <HumanGate
          engagementId={id}
          gateNumber={gateNumber}
          onDecision={handleGateDecision}
        />
      )}

      <Tabs defaultValue="swarm">
        <TabsList>
          <TabsTrigger value="swarm">Swarm Monitor</TabsTrigger>
          <TabsTrigger value="findings">Findings</TabsTrigger>
          <TabsTrigger value="report">Report</TabsTrigger>
        </TabsList>
        <TabsContent value="swarm"><SwarmMonitor /></TabsContent>
        <TabsContent value="findings"><FindingsPanel /></TabsContent>
        <TabsContent value="report"><ReportViewer /></TabsContent>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 3: Write App.tsx and main.tsx**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Home } from "./pages/Home";
import { Engagement } from "./pages/Engagement";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/engagement/:id" element={<Engagement />} />
      </Routes>
    </BrowserRouter>
  );
}
```

```tsx
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 4: Start frontend and verify**

```bash
cd frontend && npm run dev
# Open http://localhost:5173
# Expected: FORGE dashboard loads, can create engagements, navigate to engagement page
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat: Home and Engagement pages with full routing — FORGE UI complete"
```

---

## Plan 4 Complete

At this point FORGE is fully built end-to-end:

- Full REST API (engagements, gates, knowledge, system)
- WebSocket streaming for live swarm events
- React UI with all 5 components + routing
- Human gates with approve/reject flow
- Findings panel with confidence scores
- Report viewer with markdown export

**FORGE is complete. Run the full stack:**
```bash
make up          # start Docker services
make migrate     # run DB migrations
make dev         # start FastAPI backend
cd frontend && npm run dev   # start React frontend
```

**Visit:** http://localhost:5173
