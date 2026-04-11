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
