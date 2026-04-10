# backend/app/knowledge/vector_store.py
import uuid as _uuid_module
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from app.config import settings

VECTOR_SIZE = 1536


class VectorStore:
    def __init__(self, url: str = None, collection: str = "forge_knowledge"):
        self._url = url or settings.qdrant_url
        self._collection = collection
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(url=self._url)
            collections = await self._client.get_collections()
            names = [c.name for c in collections.collections]
            if self._collection not in names:
                await self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                )
        return self._client

    async def _embed(self, text: str) -> list[float]:
        """Deterministic hash-based embedding for dev. Replace with real embeddings in production."""
        import hashlib
        import struct
        h = hashlib.sha256(text.encode()).digest()
        needed = VECTOR_SIZE * 4
        repeated = (h * (needed // len(h) + 1))[:needed]
        floats = [struct.unpack_from("f", repeated, i * 4)[0] for i in range(VECTOR_SIZE)]
        magnitude = sum(f * f for f in floats) ** 0.5 or 1.0
        return [f / magnitude for f in floats]

    @staticmethod
    def _normalize_id(entry_id: str) -> str:
        """Convert arbitrary string IDs to UUID format required by Qdrant."""
        try:
            # Already a valid UUID?
            _uuid_module.UUID(entry_id)
            return entry_id
        except ValueError:
            # Derive a deterministic UUID5 from the string
            return str(_uuid_module.uuid5(_uuid_module.NAMESPACE_DNS, entry_id))

    async def upsert(self, entry_id: str, text: str, payload: dict) -> None:
        client = await self._get_client()
        vector = await self._embed(text)
        point = PointStruct(id=self._normalize_id(entry_id), vector=vector, payload={**payload, "_entry_id": entry_id})
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
            points_selector=[self._normalize_id(entry_id)],
        )
