# backend/app/knowledge/query.py
from app.knowledge.vector_store import VectorStore
from app.knowledge.graph_store import GraphStore


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
