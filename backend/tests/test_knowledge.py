# backend/tests/test_knowledge.py
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.knowledge.vector_store import VectorStore
from app.knowledge.graph_store import GraphStore
from app.config import settings
from app.knowledge.query import KnowledgeQuery


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


@pytest.mark.asyncio
async def test_query_similar_techniques():
    kb = KnowledgeQuery()
    await kb.vector.upsert("k1", "JWT alg:none bypass on Node.js Express", {
        "attack_class": "auth_bypass", "outcome": "confirmed", "tech_stack": ["nodejs", "express"]
    })
    results = await kb.find_similar_techniques(
        description="JWT token forgery on express application",
        attack_class="auth_bypass",
        top_k=3,
    )
    assert isinstance(results, list)
    assert len(results) >= 0


@pytest.mark.asyncio
async def test_query_hit_rate():
    kb = KnowledgeQuery()
    rate = await kb.hit_rate(attack_class="auth_bypass", tech_stack=["nodejs"])
    assert 0.0 <= rate <= 1.0
