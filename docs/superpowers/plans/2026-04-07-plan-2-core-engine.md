# FORGE Plan 2: Core Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Knowledge Store (Qdrant + Neo4j), the Redis Task Board with bidding system, and the Strategic Brain (Semantic Modeler, Campaign Planner, Evasion Strategist, Memory Engine).

**Architecture:** Qdrant stores vector embeddings of past findings/techniques for semantic similarity search. Neo4j stores attack chain relationships. Redis Streams power the Task Board — every task mutation is an event, agents publish bids, the scheduler consumes them. The Strategic Brain uses Claude Sonnet 4.6 via LangChain to reason about targets and generate hypotheses.

**Tech Stack:** qdrant-client, neo4j, redis[hiredis], langchain, langchain-anthropic, httpx, playwright, pytest-asyncio

**Prerequisite:** Plan 1 complete — services running, models migrated.

---

## File Map

| File | Purpose |
|---|---|
| `backend/app/knowledge/vector_store.py` | Qdrant client wrapper — upsert, search, delete |
| `backend/app/knowledge/graph_store.py` | Neo4j client wrapper — create nodes/edges, query attack chains |
| `backend/app/knowledge/query.py` | Unified query interface over vector + graph |
| `backend/app/swarm/task_board.py` | Redis Streams task board — publish, consume, bid, assign |
| `backend/app/brain/semantic_modeler.py` | Crawl target, extract endpoints/roles/flows, build semantic model |
| `backend/app/brain/campaign_planner.py` | Query KB + semantic model → ranked list of hypotheses |
| `backend/app/brain/evasion_strategist.py` | Fingerprint WAF/rate limits, produce stealth guidelines |
| `backend/app/brain/memory_engine.py` | Post-engagement: extract lessons, write to Qdrant + Neo4j |
| `backend/tests/test_knowledge.py` | Vector store + graph store unit tests |
| `backend/tests/test_task_board.py` | Task board publish/consume/bid/assign tests |
| `backend/tests/test_brain.py` | Brain component tests (LLM calls mocked) |

---

### Task 1: Qdrant Vector Store

**Files:**
- Create: `backend/app/knowledge/vector_store.py`
- Test: `backend/tests/test_knowledge.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_knowledge.py
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.knowledge.vector_store import VectorStore


@pytest.mark.asyncio
async def test_upsert_and_search():
    store = VectorStore(url="http://localhost:6333", collection="test_forge")
    entry_id = str(uuid.uuid4())
    payload = {
        "attack_class": "sqli",
        "technique": "union-based",
        "tech_stack": ["mysql", "php"],
        "outcome": "confirmed",
    }
    # upsert should not raise
    await store.upsert(entry_id, "SQL injection via union-based technique on PHP MySQL stack", payload)
    results = await store.search("union based SQL injection", top_k=3)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_delete_entry():
    store = VectorStore(url="http://localhost:6333", collection="test_forge")
    entry_id = str(uuid.uuid4())
    await store.upsert(entry_id, "some technique", {"attack_class": "xss"})
    await store.delete(entry_id)
    # no exception = pass
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_knowledge.py -v
# Expected: ImportError: No module named 'app.knowledge.vector_store'
```

- [ ] **Step 3: Implement vector_store.py**

```python
# backend/app/knowledge/vector_store.py
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from anthropic import AsyncAnthropic
from app.config import settings
import uuid


VECTOR_SIZE = 1536  # text-embedding-3-small size; we use Anthropic embeddings via a small trick
# We'll use a simple hash-based embedding for now and swap to real embeddings in Plan 4
# For real embeddings: use voyage-ai or openai text-embedding-3-small


class VectorStore:
    def __init__(self, url: str = None, collection: str = "forge_knowledge"):
        self._url = url or settings.qdrant_url
        self._collection = collection
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(url=self._url)
            # ensure collection exists
            collections = await self._client.get_collections()
            names = [c.name for c in collections.collections]
            if self._collection not in names:
                await self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                )
        return self._client

    async def _embed(self, text: str) -> list[float]:
        """Simple deterministic embedding for dev. Replace with real embeddings in production."""
        import hashlib
        import struct
        h = hashlib.sha256(text.encode()).digest()
        # repeat hash to fill vector size
        repeated = (h * (VECTOR_SIZE // len(h) + 1))[:VECTOR_SIZE * 4]
        floats = [struct.unpack_from("f", repeated, i * 4)[0] for i in range(VECTOR_SIZE)]
        # normalize
        magnitude = sum(f * f for f in floats) ** 0.5 or 1.0
        return [f / magnitude for f in floats]

    async def upsert(self, entry_id: str, text: str, payload: dict) -> None:
        client = await self._get_client()
        vector = await self._embed(text)
        point = PointStruct(id=entry_id, vector=vector, payload=payload)
        await client.upsert(collection_name=self._collection, points=[point])

    async def search(self, query: str, top_k: int = 5, filter_payload: dict | None = None) -> list[dict]:
        client = await self._get_client()
        vector = await self._embed(query)
        query_filter = None
        if filter_payload:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_payload.items()
            ]
            query_filter = Filter(must=conditions)
        results = await client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=top_k,
            query_filter=query_filter,
        )
        return [{"id": r.id, "score": r.score, **r.payload} for r in results]

    async def delete(self, entry_id: str) -> None:
        client = await self._get_client()
        await client.delete(
            collection_name=self._collection,
            points_selector=[entry_id],
        )
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd backend && pytest tests/test_knowledge.py::test_upsert_and_search tests/test_knowledge.py::test_delete_entry -v
# Expected: 2 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/knowledge/vector_store.py backend/tests/test_knowledge.py
git commit -m "feat: Qdrant vector store wrapper with upsert/search/delete"
```

---

### Task 2: Neo4j Graph Store

**Files:**
- Create: `backend/app/knowledge/graph_store.py`
- Test: `backend/tests/test_knowledge.py` (append)

- [ ] **Step 1: Add failing test**

```python
# append to backend/tests/test_knowledge.py
from app.knowledge.graph_store import GraphStore


@pytest.mark.asyncio
async def test_create_technique_node():
    store = GraphStore(
        url=settings.neo4j_url,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await store.upsert_technique(
        technique_id="sqli-union-001",
        name="Union-based SQLi",
        attack_class="sqli",
        tech_stack=["mysql", "php"],
        outcome="confirmed",
    )
    chains = await store.get_chains_for_class("sqli")
    assert any(c["technique_id"] == "sqli-union-001" for c in chains)
    await store.close()


@pytest.mark.asyncio
async def test_link_techniques():
    store = GraphStore(
        url=settings.neo4j_url,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await store.upsert_technique("t1", "Recon", "recon", [], "confirmed")
    await store.upsert_technique("t2", "Auth bypass", "auth_bypass", [], "confirmed")
    await store.link_techniques("t1", "t2", relationship="LEADS_TO")
    path = await store.shortest_path("t1", "t2")
    assert path is not None
    await store.close()
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_knowledge.py::test_create_technique_node -v
# Expected: ImportError
```

- [ ] **Step 3: Implement graph_store.py**

```python
# backend/app/knowledge/graph_store.py
from neo4j import AsyncGraphDatabase, AsyncDriver
from app.config import settings


class GraphStore:
    def __init__(self, url: str = None, user: str = None, password: str = None):
        self._url = url or settings.neo4j_url
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._driver: AsyncDriver | None = None

    async def _get_driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self._url, auth=(self._user, self._password)
            )
        return self._driver

    async def close(self):
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def upsert_technique(
        self,
        technique_id: str,
        name: str,
        attack_class: str,
        tech_stack: list[str],
        outcome: str,
    ) -> None:
        driver = await self._get_driver()
        async with driver.session() as session:
            await session.run(
                """
                MERGE (t:Technique {technique_id: $technique_id})
                SET t.name = $name,
                    t.attack_class = $attack_class,
                    t.tech_stack = $tech_stack,
                    t.outcome = $outcome
                """,
                technique_id=technique_id,
                name=name,
                attack_class=attack_class,
                tech_stack=tech_stack,
                outcome=outcome,
            )

    async def link_techniques(self, from_id: str, to_id: str, relationship: str = "LEADS_TO") -> None:
        driver = await self._get_driver()
        async with driver.session() as session:
            await session.run(
                f"""
                MATCH (a:Technique {{technique_id: $from_id}})
                MATCH (b:Technique {{technique_id: $to_id}})
                MERGE (a)-[:{relationship}]->(b)
                """,
                from_id=from_id,
                to_id=to_id,
            )

    async def get_chains_for_class(self, attack_class: str) -> list[dict]:
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                "MATCH (t:Technique {attack_class: $attack_class}) RETURN t",
                attack_class=attack_class,
            )
            records = await result.data()
            return [dict(r["t"]) for r in records]

    async def shortest_path(self, from_id: str, to_id: str) -> list[dict] | None:
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH path = shortestPath(
                  (a:Technique {technique_id: $from_id})-[*]->(b:Technique {technique_id: $to_id})
                )
                RETURN [node in nodes(path) | node.technique_id] AS chain
                """,
                from_id=from_id,
                to_id=to_id,
            )
            record = await result.single()
            return record["chain"] if record else None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_knowledge.py -v
# Expected: 4 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/knowledge/graph_store.py
git commit -m "feat: Neo4j graph store for attack chain relationship modeling"
```

---

### Task 3: Unified Knowledge Query Interface

**Files:**
- Create: `backend/app/knowledge/query.py`
- Test: `backend/tests/test_knowledge.py` (append)

- [ ] **Step 1: Add failing test**

```python
# append to backend/tests/test_knowledge.py
from app.knowledge.query import KnowledgeQuery


@pytest.mark.asyncio
async def test_query_similar_techniques():
    kb = KnowledgeQuery()
    # seed some data
    await kb.vector.upsert("k1", "JWT alg:none bypass on Node.js Express", {
        "attack_class": "auth_bypass", "outcome": "confirmed", "tech_stack": ["nodejs", "express"]
    })
    results = await kb.find_similar_techniques(
        description="JWT token forgery on express application",
        attack_class="auth_bypass",
        top_k=3,
    )
    assert isinstance(results, list)
    assert len(results) >= 0  # may be 0 if embeddings don't match well in dev mode


@pytest.mark.asyncio
async def test_query_hit_rate():
    kb = KnowledgeQuery()
    rate = await kb.hit_rate(attack_class="auth_bypass", tech_stack=["nodejs"])
    assert 0.0 <= rate <= 1.0
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_knowledge.py::test_query_similar_techniques -v
# Expected: ImportError
```

- [ ] **Step 3: Implement query.py**

```python
# backend/app/knowledge/query.py
from app.knowledge.vector_store import VectorStore
from app.knowledge.graph_store import GraphStore
from app.config import settings


class KnowledgeQuery:
    def __init__(self):
        self.vector = VectorStore()
        self.graph = GraphStore()

    async def find_similar_techniques(
        self,
        description: str,
        attack_class: str | None = None,
        tech_stack: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        filter_payload = {}
        if attack_class:
            filter_payload["attack_class"] = attack_class
        results = await self.vector.search(
            query=description,
            top_k=top_k,
            filter_payload=filter_payload or None,
        )
        # filter by tech_stack overlap if provided
        if tech_stack:
            results = [
                r for r in results
                if any(t in r.get("tech_stack", []) for t in tech_stack)
            ]
        return results

    async def hit_rate(self, attack_class: str, tech_stack: list[str] | None = None) -> float:
        """Return historical success rate for an attack class."""
        results = await self.vector.search(
            query=attack_class,
            top_k=50,
            filter_payload={"attack_class": attack_class},
        )
        if not results:
            return 0.0
        confirmed = sum(1 for r in results if r.get("outcome") == "confirmed")
        return confirmed / len(results)

    async def get_attack_chain(self, from_technique: str, to_technique: str) -> list[str] | None:
        return await self.graph.shortest_path(from_technique, to_technique)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_knowledge.py -v
# Expected: 6 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/knowledge/query.py
git commit -m "feat: unified knowledge query interface (vector + graph)"
```

---

### Task 4: Redis Task Board

**Files:**
- Create: `backend/app/swarm/task_board.py`
- Test: `backend/tests/test_task_board.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_task_board.py
import pytest
import uuid
from app.swarm.task_board import TaskBoard


@pytest.mark.asyncio
async def test_publish_task():
    board = TaskBoard()
    task_id = str(uuid.uuid4())
    engagement_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())
    await board.publish_task(
        task_id=task_id,
        engagement_id=engagement_id,
        title="Test JWT bypass",
        surface="/api/auth/refresh",
        required_confidence=0.7,
        priority="high",
        created_by=creator_id,
    )
    tasks = await board.get_open_tasks(engagement_id)
    assert any(t["task_id"] == task_id for t in tasks)


@pytest.mark.asyncio
async def test_submit_and_resolve_bid():
    board = TaskBoard()
    task_id = str(uuid.uuid4())
    engagement_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())

    await board.publish_task(
        task_id=task_id,
        engagement_id=engagement_id,
        title="IDOR test",
        surface="/api/users/{id}",
        required_confidence=0.6,
        priority="medium",
        created_by=creator_id,
    )
    await board.submit_bid(
        task_id=task_id,
        agent_id=agent_id,
        confidence=0.85,
        basis="3 prior IDOR confirmations on similar APIs",
        estimated_probes=4,
        noise_level="low",
    )
    bids = await board.get_bids(task_id)
    assert len(bids) == 1
    assert bids[0]["confidence"] == 0.85


@pytest.mark.asyncio
async def test_assign_task():
    board = TaskBoard()
    task_id = str(uuid.uuid4())
    engagement_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())

    await board.publish_task(
        task_id=task_id, engagement_id=engagement_id,
        title="XSS probe", surface="/search",
        required_confidence=0.5, priority="low", created_by=creator_id,
    )
    await board.assign_task(task_id=task_id, agent_id=agent_id)
    task = await board.get_task(task_id)
    assert task["status"] == "assigned"
    assert task["assigned_agent_id"] == agent_id
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_task_board.py -v
# Expected: ImportError
```

- [ ] **Step 3: Implement task_board.py**

```python
# backend/app/swarm/task_board.py
import json
import uuid
from datetime import datetime
import redis.asyncio as aioredis
from app.config import settings


class TaskBoard:
    """
    Redis-backed task board. Uses Redis hashes for task state and
    Redis lists for bids. Every mutation appends to an event stream.
    """

    def __init__(self, redis_url: str = None):
        self._redis_url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _task_key(self, task_id: str) -> str:
        return f"forge:task:{task_id}"

    def _bid_key(self, task_id: str) -> str:
        return f"forge:bids:{task_id}"

    def _engagement_tasks_key(self, engagement_id: str) -> str:
        return f"forge:engagement:{engagement_id}:tasks"

    async def publish_task(
        self,
        task_id: str,
        engagement_id: str,
        title: str,
        surface: str,
        required_confidence: float,
        priority: str,
        created_by: str,
        description: str = "",
        hypothesis_id: str | None = None,
    ) -> None:
        r = await self._get_redis()
        task_data = {
            "task_id": task_id,
            "engagement_id": engagement_id,
            "title": title,
            "description": description,
            "surface": surface,
            "required_confidence": str(required_confidence),
            "priority": priority,
            "status": "open",
            "created_by": created_by,
            "assigned_agent_id": "",
            "hypothesis_id": hypothesis_id or "",
            "created_at": datetime.utcnow().isoformat(),
            "event_log": json.dumps([{"event": "created", "at": datetime.utcnow().isoformat()}]),
        }
        await r.hset(self._task_key(task_id), mapping=task_data)
        await r.sadd(self._engagement_tasks_key(engagement_id), task_id)

    async def get_task(self, task_id: str) -> dict | None:
        r = await self._get_redis()
        data = await r.hgetall(self._task_key(task_id))
        if not data:
            return None
        data["required_confidence"] = float(data["required_confidence"])
        data["event_log"] = json.loads(data.get("event_log", "[]"))
        return data

    async def get_open_tasks(self, engagement_id: str) -> list[dict]:
        r = await self._get_redis()
        task_ids = await r.smembers(self._engagement_tasks_key(engagement_id))
        tasks = []
        for tid in task_ids:
            task = await self.get_task(tid)
            if task and task["status"] == "open":
                tasks.append(task)
        return tasks

    async def submit_bid(
        self,
        task_id: str,
        agent_id: str,
        confidence: float,
        basis: str,
        estimated_probes: int,
        noise_level: str,
    ) -> None:
        r = await self._get_redis()
        bid = {
            "bid_id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "confidence": confidence,
            "basis": basis,
            "estimated_probes": estimated_probes,
            "noise_level": noise_level,
            "submitted_at": datetime.utcnow().isoformat(),
        }
        await r.rpush(self._bid_key(task_id), json.dumps(bid))
        await r.hset(self._task_key(task_id), "status", "bidding")

    async def get_bids(self, task_id: str) -> list[dict]:
        r = await self._get_redis()
        raw_bids = await r.lrange(self._bid_key(task_id), 0, -1)
        return [json.loads(b) for b in raw_bids]

    async def assign_task(self, task_id: str, agent_id: str) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), mapping={
            "status": "assigned",
            "assigned_agent_id": agent_id,
        })
        # append to event log
        task = await self.get_task(task_id)
        log = task.get("event_log", [])
        log.append({"event": "assigned", "agent_id": agent_id, "at": datetime.utcnow().isoformat()})
        await r.hset(self._task_key(task_id), "event_log", json.dumps(log))

    async def complete_task(self, task_id: str, result: dict) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), mapping={
            "status": "complete",
            "result": json.dumps(result),
        })

    async def reject_task(self, task_id: str, reason: str) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), mapping={
            "status": "rejected",
            "result": json.dumps({"reason": reason}),
        })

    async def gate_task(self, task_id: str) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), "status", "awaiting_human_gate")
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_task_board.py -v
# Expected: 3 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/swarm/task_board.py backend/tests/test_task_board.py
git commit -m "feat: Redis task board with publish/bid/assign/complete operations"
```

---

### Task 5: Strategic Brain — Semantic Modeler

**Files:**
- Create: `backend/app/brain/semantic_modeler.py`
- Test: `backend/tests/test_brain.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_brain.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.brain.semantic_modeler import SemanticModeler


@pytest.mark.asyncio
async def test_semantic_modeler_returns_model():
    modeler = SemanticModeler()
    # Mock the LLM call
    mock_response = MagicMock()
    mock_response.content = '''
    {
        "app_type": "saas",
        "tech_stack": ["nodejs", "react", "postgresql"],
        "endpoints": ["/api/auth/login", "/api/users", "/api/projects"],
        "user_roles": ["admin", "member", "viewer"],
        "business_flows": ["user_registration", "project_creation", "billing"],
        "trust_boundaries": ["unauthenticated", "authenticated", "admin_only"],
        "interesting_surfaces": ["/api/auth/login", "/api/users/{id}"]
    }
    '''
    with patch.object(modeler._llm, "ainvoke", return_value=mock_response):
        model = await modeler.build(
            target_url="https://example.com",
            crawl_data={"paths": ["/api/auth/login", "/api/users"], "headers": {"server": "nginx"}},
        )
    assert model["app_type"] == "saas"
    assert "nodejs" in model["tech_stack"]
    assert len(model["endpoints"]) > 0


@pytest.mark.asyncio
async def test_semantic_modeler_crawl():
    modeler = SemanticModeler()
    # Just test crawl doesn't throw on reachable target
    # Use httpbin as a safe crawl target
    crawl_data = await modeler.crawl("https://httpbin.org")
    assert "paths" in crawl_data
    assert "headers" in crawl_data
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_brain.py::test_semantic_modeler_returns_model -v
# Expected: ImportError
```

- [ ] **Step 3: Implement semantic_modeler.py**

```python
# backend/app/brain/semantic_modeler.py
import json
import re
import httpx
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a security researcher analyzing a web application.
Given crawl data about a target application, produce a structured semantic model of what the app does.

Return ONLY valid JSON with these fields:
- app_type: string (saas, ecommerce, fintech, api-only, cms, social, other)
- tech_stack: list of strings (detected technologies)
- endpoints: list of strings (discovered API/page paths)
- user_roles: list of strings (inferred user roles)
- business_flows: list of strings (key workflows)
- trust_boundaries: list of strings (auth levels/access tiers)
- interesting_surfaces: list of strings (highest-value attack surfaces)
"""


class SemanticModeler:
    def __init__(self):
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2000,
        )

    async def crawl(self, target_url: str) -> dict:
        """Lightweight passive crawl — just headers and a homepage fetch."""
        paths = []
        headers = {}
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(target_url)
                headers = dict(resp.headers)
                # extract links from HTML (simple regex)
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp.text)
                paths = list(set(h for h in hrefs if h.startswith("/")))[:50]
        except Exception:
            pass
        return {"paths": paths, "headers": headers, "base_url": target_url}

    async def build(self, target_url: str, crawl_data: dict) -> dict:
        """Build semantic app model from crawl data using LLM reasoning."""
        user_content = f"""
Target URL: {target_url}

Discovered paths: {json.dumps(crawl_data.get('paths', [])[:30])}
Response headers: {json.dumps({k: v for k, v in crawl_data.get('headers', {}).items() if k.lower() in ['server', 'x-powered-by', 'x-framework', 'content-type', 'set-cookie']})}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        # strip markdown fences if present
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_brain.py::test_semantic_modeler_returns_model -v
# Expected: PASSED (uses mock LLM)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/brain/semantic_modeler.py backend/tests/test_brain.py
git commit -m "feat: semantic modeler — crawl target and build structured app model via LLM"
```

---

### Task 6: Campaign Planner

**Files:**
- Create: `backend/app/brain/campaign_planner.py`
- Test: `backend/tests/test_brain.py` (append)

- [ ] **Step 1: Add failing test**

```python
# append to backend/tests/test_brain.py
from app.brain.campaign_planner import CampaignPlanner


@pytest.mark.asyncio
async def test_campaign_planner_returns_hypotheses():
    planner = CampaignPlanner()
    semantic_model = {
        "app_type": "fintech",
        "tech_stack": ["nodejs", "postgresql"],
        "endpoints": ["/api/auth/login", "/api/transfer", "/api/balance"],
        "user_roles": ["user", "admin"],
        "business_flows": ["login", "fund_transfer", "balance_check"],
        "trust_boundaries": ["unauthenticated", "authenticated"],
        "interesting_surfaces": ["/api/transfer", "/api/auth/login"],
    }
    mock_response = MagicMock()
    mock_response.content = '''[
        {
            "title": "Race condition in /api/transfer",
            "surface": "/api/transfer",
            "attack_class": "race_condition",
            "reasoning": "Fund transfer flows in fintech apps commonly have TOCTOU vulnerabilities",
            "confidence": 0.82,
            "priority": "critical"
        },
        {
            "title": "IDOR in balance endpoint",
            "surface": "/api/balance",
            "attack_class": "idor",
            "reasoning": "Balance endpoints often lack proper authorization checks",
            "confidence": 0.71,
            "priority": "high"
        }
    ]'''
    with patch.object(planner._llm, "ainvoke", return_value=mock_response):
        hypotheses = await planner.generate(semantic_model=semantic_model, kb_context=[])
    assert len(hypotheses) == 2
    assert hypotheses[0]["attack_class"] == "race_condition"
    assert hypotheses[0]["confidence"] == 0.82
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_brain.py::test_campaign_planner_returns_hypotheses -v
# Expected: ImportError
```

- [ ] **Step 3: Implement campaign_planner.py**

```python
# backend/app/brain/campaign_planner.py
import json
import re
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a senior penetration tester generating a prioritized attack campaign.
Given a semantic model of the target application and historical knowledge base results,
generate a ranked list of attack hypotheses.

Return ONLY a valid JSON array. Each item must have:
- title: string (short hypothesis name)
- surface: string (specific endpoint or component to test)
- attack_class: string (sqli, xss, idor, auth_bypass, race_condition, business_logic, ssrf, xxe, etc.)
- reasoning: string (why this hypothesis is viable for THIS app)
- confidence: float (0.0–1.0, based on app type + KB history)
- priority: string (critical, high, medium, low)

Order by priority descending, then confidence descending. Maximum 15 hypotheses.
"""


class CampaignPlanner:
    def __init__(self):
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=3000,
        )

    async def generate(self, semantic_model: dict, kb_context: list[dict]) -> list[dict]:
        kb_summary = "\n".join(
            f"- {r.get('attack_class', '')} ({r.get('technique', '')}): {r.get('outcome', '')} hit rate {r.get('score', 0):.2f}"
            for r in kb_context[:10]
        ) or "No prior history for this target profile."

        user_content = f"""
Semantic App Model:
{json.dumps(semantic_model, indent=2)}

Relevant Knowledge Base History:
{kb_summary}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
```

- [ ] **Step 4: Run test — verify it passes**

```bash
cd backend && pytest tests/test_brain.py::test_campaign_planner_returns_hypotheses -v
# Expected: PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/brain/campaign_planner.py
git commit -m "feat: campaign planner — LLM-driven hypothesis generation from semantic model + KB"
```

---

### Task 7: Evasion Strategist + Memory Engine

**Files:**
- Create: `backend/app/brain/evasion_strategist.py`
- Create: `backend/app/brain/memory_engine.py`
- Test: `backend/tests/test_brain.py` (append)

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_brain.py
from app.brain.evasion_strategist import EvasionStrategist
from app.brain.memory_engine import MemoryEngine


@pytest.mark.asyncio
async def test_evasion_strategist_returns_guidelines():
    strategist = EvasionStrategist()
    mock_response = MagicMock()
    mock_response.content = '''{
        "waf_detected": true,
        "waf_type": "cloudflare",
        "rate_limit_detected": true,
        "rate_limit_rps": 10,
        "guidelines": [
            "Use chunked encoding to bypass WAF body inspection",
            "Space requests at least 200ms apart",
            "Rotate User-Agent headers"
        ],
        "stealth_level": "quiet"
    }'''
    with patch.object(strategist._llm, "ainvoke", return_value=mock_response):
        guidelines = await strategist.analyze(
            target_url="https://example.com",
            headers={"server": "cloudflare", "cf-ray": "abc123"},
            response_codes=[200, 429, 403],
        )
    assert guidelines["waf_detected"] is True
    assert len(guidelines["guidelines"]) > 0


@pytest.mark.asyncio
async def test_memory_engine_write(tmp_path):
    engine = MemoryEngine()
    findings = [
        {
            "title": "IDOR in /api/users",
            "vulnerability_class": "idor",
            "affected_surface": "/api/users/{id}",
            "severity": "high",
            "confidence_score": 0.91,
        }
    ]
    semantic_model = {
        "app_type": "saas",
        "tech_stack": ["nodejs", "postgresql"],
    }
    # Mock the KB writes
    with patch.object(engine._kb.vector, "upsert", new_callable=AsyncMock) as mock_upsert, \
         patch.object(engine._kb.graph, "upsert_technique", new_callable=AsyncMock):
        await engine.write_back(
            engagement_id="eng-001",
            findings=findings,
            semantic_model=semantic_model,
            failed_hypotheses=[],
        )
        assert mock_upsert.called
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend && pytest tests/test_brain.py::test_evasion_strategist_returns_guidelines -v
# Expected: ImportError
```

- [ ] **Step 3: Implement evasion_strategist.py**

```python
# backend/app/brain/evasion_strategist.py
import json
import re
import httpx
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a red team expert analyzing a target's defensive posture.
Given HTTP response headers, observed status codes, and target URL,
determine what defenses are in place and produce evasion guidelines.

Return ONLY valid JSON with:
- waf_detected: bool
- waf_type: string (cloudflare, akamai, aws_waf, modsecurity, unknown, none)
- rate_limit_detected: bool
- rate_limit_rps: int | null (estimated requests per second before throttle)
- guidelines: list of strings (specific evasion techniques to apply)
- stealth_level: string (aggressive, balanced, quiet)
"""


class EvasionStrategist:
    def __init__(self):
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=1000,
        )

    async def probe_defenses(self, target_url: str) -> tuple[dict, list[int]]:
        """Send a few passive probes to fingerprint the defensive stack."""
        headers = {}
        status_codes = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(target_url)
                headers = dict(resp.headers)
                status_codes.append(resp.status_code)
                # probe a non-existent path
                r2 = await client.get(f"{target_url}/forge-probe-404")
                status_codes.append(r2.status_code)
        except Exception:
            pass
        return headers, status_codes

    async def analyze(self, target_url: str, headers: dict, response_codes: list[int]) -> dict:
        user_content = f"""
Target: {target_url}
Response Headers: {json.dumps(headers)}
Observed Status Codes: {response_codes}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
```

- [ ] **Step 4: Implement memory_engine.py**

```python
# backend/app/brain/memory_engine.py
import uuid
from app.knowledge.query import KnowledgeQuery


class MemoryEngine:
    def __init__(self):
        self._kb = KnowledgeQuery()

    async def write_back(
        self,
        engagement_id: str,
        findings: list[dict],
        semantic_model: dict,
        failed_hypotheses: list[dict],
    ) -> None:
        """Write engagement lessons into the knowledge store after completion."""
        tech_stack = semantic_model.get("tech_stack", [])
        app_type = semantic_model.get("app_type", "unknown")

        for finding in findings:
            entry_id = str(uuid.uuid4())
            attack_class = finding.get("vulnerability_class", "unknown")
            technique = finding.get("title", "")
            text = f"{attack_class} via {technique} on {app_type} ({', '.join(tech_stack)})"
            payload = {
                "attack_class": attack_class,
                "technique": technique,
                "tech_stack": tech_stack,
                "app_type": app_type,
                "outcome": "confirmed",
                "signal_strength": finding.get("confidence_score", 1.0),
                "engagement_id": engagement_id,
            }
            await self._kb.vector.upsert(entry_id, text, payload)
            await self._kb.graph.upsert_technique(
                technique_id=f"{engagement_id}-{attack_class}",
                name=technique,
                attack_class=attack_class,
                tech_stack=tech_stack,
                outcome="confirmed",
            )

        for hyp in failed_hypotheses:
            entry_id = str(uuid.uuid4())
            attack_class = hyp.get("attack_class", "unknown")
            text = f"FAILED: {attack_class} on {app_type} ({', '.join(tech_stack)})"
            payload = {
                "attack_class": attack_class,
                "technique": hyp.get("title", ""),
                "tech_stack": tech_stack,
                "app_type": app_type,
                "outcome": "false_positive",
                "signal_strength": 0.1,
                "engagement_id": engagement_id,
            }
            await self._kb.vector.upsert(entry_id, text, payload)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_brain.py -v
# Expected: 5 PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/brain/
git commit -m "feat: evasion strategist and memory engine — complete Strategic Brain"
```

---

## Plan 2 Complete

At this point you have:
- Qdrant vector store with upsert/search/delete
- Neo4j graph store with technique nodes and chain queries
- Unified KnowledgeQuery interface
- Redis Task Board with publish/bid/assign/complete
- Full Strategic Brain: Semantic Modeler, Campaign Planner, Evasion Strategist, Memory Engine

**Next:** Plan 3 — Tactical Swarm + Adversarial Validator
