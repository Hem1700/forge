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
