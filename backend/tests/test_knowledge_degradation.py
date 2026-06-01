# backend/tests/test_knowledge_degradation.py
"""Knowledge layer degrades gracefully when Neo4j/Qdrant are unavailable."""
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_graph_store_is_available_false_on_connection_error():
    from app.knowledge.graph_store import GraphStore
    # Dead port → driver connect/RETURN 1 fails → False (never raises)
    store = GraphStore(url="bolt://localhost:19999", user="x", password="y")
    assert await store.is_available() is False


@pytest.mark.asyncio
async def test_vector_store_is_available_false_on_connection_error():
    from app.knowledge.vector_store import VectorStore
    store = VectorStore(url="http://localhost:19999")
    assert await store.is_available() is False


@pytest.mark.asyncio
async def test_find_similar_techniques_empty_when_qdrant_down():
    from app.knowledge.query import KnowledgeQuery
    kq = KnowledgeQuery()
    kq.vector = AsyncMock()
    kq.vector.is_available = AsyncMock(return_value=False)
    result = await kq.find_similar_techniques(description="sqli", attack_class="sql_injection")
    assert result == []
    kq.vector.search.assert_not_called()  # short-circuited before hitting the store


@pytest.mark.asyncio
async def test_hit_rate_zero_when_qdrant_down():
    from app.knowledge.query import KnowledgeQuery
    kq = KnowledgeQuery()
    kq.vector = AsyncMock()
    kq.vector.is_available = AsyncMock(return_value=False)
    assert await kq.hit_rate(attack_class="sql_injection") == 0.0


@pytest.mark.asyncio
async def test_get_attack_chain_none_when_neo4j_down():
    from app.knowledge.query import KnowledgeQuery
    kq = KnowledgeQuery()
    kq.graph = AsyncMock()
    kq.graph.is_available = AsyncMock(return_value=False)
    result = await kq.get_attack_chain("a", "b")
    assert result is None
    kq.graph.shortest_path.assert_not_called()


@pytest.mark.asyncio
async def test_find_similar_techniques_works_when_qdrant_up():
    from app.knowledge.query import KnowledgeQuery
    kq = KnowledgeQuery()
    kq.vector = AsyncMock()
    kq.vector.is_available = AsyncMock(return_value=True)
    kq.vector.search = AsyncMock(return_value=[
        {"id": "1", "attack_class": "sql_injection", "tech_stack": ["python"]},
    ])
    result = await kq.find_similar_techniques(description="sqli", attack_class="sql_injection")
    assert len(result) == 1
