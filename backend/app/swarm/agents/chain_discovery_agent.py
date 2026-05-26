# backend/app/swarm/agents/chain_discovery_agent.py
"""ChainDiscoveryAgent — correlates findings from the 5 OS scanning agents to
discover multi-step attack chains.

Builds a directed "ENABLES" graph between findings using deterministic heuristics,
optionally persists it to Neo4j (with in-memory fallback when Neo4j is
unavailable), enumerates 2-4 hop paths, and asks the HEAVY-tier LLM to
synthesize each path into a coherent attack narrative.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from app.brain.llm_factory import TaskType, get_llm
from app.knowledge.graph_store import GraphStore
from app.swarm.agents.base import BaseAgent
from app.ws import progress as ws_progress

logger = logging.getLogger(__name__)


_CHAIN_SYSTEM_PROMPT = (
    "You are a senior red-team operator. Analyze these attack paths on a "
    "single Linux system. For each viable multi-step chain: describe each "
    "step an attacker would take, explain why the individual findings seem "
    "low-risk in isolation but dangerous in combination, assign overall "
    "severity (consider that any path to root = CRITICAL), and estimate "
    "time-to-exploit for a skilled attacker."
)

# Severities considered "high risk" when combined.
_HIGH_RISK_SEVERITIES = {"critical", "high"}

# Maximum number of paths to feed into the LLM.
_MAX_PATHS = 20

# Path-length bounds (inclusive) for chain enumeration.
_MIN_HOPS = 2
_MAX_HOPS = 4


@dataclass
class ChainDiscoveryAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        raw_findings: list[dict] = task.get("findings", []) or []
        org_id = task.get("org_id")

        # Empty input — short-circuit before doing any work.
        if not raw_findings:
            await ws_progress.progress(
                self.engagement_id, "chain_discovery.skipped",
                "ChainDiscoveryAgent: no findings to chain",
            )
            self.signal_history.append(0.4)
            return {
                "agent_type": self.agent_type,
                "agent_id": self.agent_id,
                "findings": [],
                "chains_discovered": 0,
            }

        # 1. Assign stable UUIDs to each finding and build a working index.
        indexed: list[dict] = []
        for f in raw_findings:
            indexed.append({
                "id": str(uuid.uuid4()),
                "vulnerability": f.get("vulnerability", ""),
                "severity": (f.get("severity") or "").lower(),
                "description": f.get("description", ""),
                "evidence": f.get("evidence", ""),
                "recommendation": f.get("recommendation", ""),
                "chain_potential": bool(f.get("chain_potential", False)),
                "confidence_score": f.get("confidence_score", 0.5),
            })

        # 2. Compute deterministic ENABLES edges.
        edges = _build_edges(indexed)

        await ws_progress.progress(
            self.engagement_id, "chain_discovery.graph_built",
            f"Built finding graph: {len(indexed)} nodes, {len(edges)} edges",
        )

        # 3. Try to persist to Neo4j (best-effort). Always fall back to in-memory.
        paths_from_neo4j: list[list[str]] = []
        try:
            paths_from_neo4j = await _persist_and_query_neo4j(indexed, edges)
            if paths_from_neo4j:
                await ws_progress.progress(
                    self.engagement_id, "chain_discovery.neo4j_paths",
                    f"Neo4j returned {len(paths_from_neo4j)} candidate paths",
                )
        except Exception:
            logger.exception(
                "ChainDiscoveryAgent: Neo4j unavailable, using in-memory fallback only",
            )
            paths_from_neo4j = []

        # 4. In-memory DFS — always run as supplement / fallback.
        in_memory_paths = _enumerate_paths_in_memory(indexed, edges)

        # Merge & dedupe (preserve order; cap at _MAX_PATHS).
        all_paths = _dedupe_paths(paths_from_neo4j + in_memory_paths)[:_MAX_PATHS]

        if not all_paths:
            await ws_progress.progress(
                self.engagement_id, "chain_discovery.done",
                "ChainDiscoveryAgent: no multi-step chains discovered",
            )
            self.signal_history.append(0.4)
            return {
                "agent_type": self.agent_type,
                "agent_id": self.agent_id,
                "findings": [],
                "chains_discovered": 0,
            }

        # 5. Hand the discovered paths to the LLM for narrative synthesis.
        findings_by_id = {f["id"]: f for f in indexed}
        llm_payload = {
            "paths": [
                {
                    "path_id": idx,
                    "finding_ids": p,
                    "findings": [
                        {
                            "id": fid,
                            "vulnerability": findings_by_id[fid]["vulnerability"],
                            "severity": findings_by_id[fid]["severity"],
                            "description": findings_by_id[fid]["description"],
                            "evidence": findings_by_id[fid]["evidence"],
                        }
                        for fid in p
                    ],
                }
                for idx, p in enumerate(all_paths)
            ]
        }

        chain_findings: list[dict] = []
        try:
            llm = await get_llm(TaskType.chain_discovery, org_id=org_id)
            messages = [
                SystemMessage(content=_CHAIN_SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(llm_payload)),
            ]
            resp = await llm.ainvoke(messages)
            chains = _parse_llm_chains(resp.content)
            for chain in chains:
                if not isinstance(chain, dict):
                    continue
                steps = chain.get("steps", []) or []
                if not isinstance(steps, list) or not steps:
                    continue
                component_ids = [
                    s.get("finding_id") for s in steps
                    if isinstance(s, dict) and s.get("finding_id")
                ]
                chain_findings.append({
                    "vulnerability": "attack_chain",
                    "vulnerability_class": "attack_chain",
                    "severity": chain.get("severity", "high"),
                    "description": chain.get("description", "Multi-step attack chain"),
                    "evidence": (
                        f"Chain: {chain.get('chain_name', 'unnamed')}\n"
                        f"Steps: {json.dumps(steps)}\n"
                        f"Time to exploit: {chain.get('time_to_exploit', 'unknown')}"
                    ),
                    "recommendation": (
                        "Address the component findings individually to break "
                        "this attack chain."
                    ),
                    "component_finding_ids": component_ids,
                    "chain_steps": steps,
                    "finding_type": "chain",
                    "confidence_score": 0.75,
                })
        except Exception:
            logger.exception("ChainDiscoveryAgent: LLM chain synthesis failed")

        await ws_progress.progress(
            self.engagement_id, "chain_discovery.done",
            f"ChainDiscoveryAgent complete — {len(chain_findings)} chains",
        )
        self.signal_history.append(1.0 if chain_findings else 0.4)
        return {
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "findings": chain_findings,
            "chains_discovered": len(chain_findings),
        }


# ── Heuristic edge construction ────────────────────────────────────────────────

def _build_edges(findings: list[dict]) -> list[tuple[str, str]]:
    """Return list of (from_id, to_id) ENABLES edges per the heuristic rules.

    Rules:
      - writable_cron_path  ENABLES suid_gtfobins
      - writable_cron_path  ENABLES docker_group_privesc
      - root_service_exposed ENABLES known_cve (severity critical/high)
      - network_exposure_bypass ENABLES root_service_exposed
      - unauthenticated_root_service ENABLES docker_group_privesc
      - any chain_potential=True ENABLES any other chain_potential=True
        where the combined severities reach critical risk
    """
    by_vuln: dict[str, list[dict]] = {}
    for f in findings:
        by_vuln.setdefault(f["vulnerability"], []).append(f)

    edges: list[tuple[str, str]] = []

    def link_all(src_vuln: str, dst_vuln: str, predicate=None) -> None:
        for src in by_vuln.get(src_vuln, []):
            for dst in by_vuln.get(dst_vuln, []):
                if src["id"] == dst["id"]:
                    continue
                if predicate is None or predicate(src, dst):
                    edges.append((src["id"], dst["id"]))

    link_all("writable_cron_path", "suid_gtfobins")
    link_all("writable_cron_path", "docker_group_privesc")
    link_all(
        "root_service_exposed", "known_cve",
        predicate=lambda s, d: d["severity"] in _HIGH_RISK_SEVERITIES,
    )
    link_all("network_exposure_bypass", "root_service_exposed")
    link_all("unauthenticated_root_service", "docker_group_privesc")

    # Generic chain_potential rule: link any two chain_potential findings whose
    # severities combine to critical risk. We define "combines to critical" as
    # at least one of the pair being in _HIGH_RISK_SEVERITIES.
    chainable = [f for f in findings if f["chain_potential"]]
    for src in chainable:
        for dst in chainable:
            if src["id"] == dst["id"]:
                continue
            if src["severity"] in _HIGH_RISK_SEVERITIES or dst["severity"] in _HIGH_RISK_SEVERITIES:
                pair = (src["id"], dst["id"])
                if pair not in edges:
                    edges.append(pair)

    return edges


# ── Neo4j persistence ──────────────────────────────────────────────────────────

async def _persist_and_query_neo4j(
    findings: list[dict],
    edges: list[tuple[str, str]],
) -> list[list[str]]:
    """Persist nodes and edges to Neo4j, then query for 2-4 hop paths.

    Returns a list of paths, each a list of finding-id strings. Raises on any
    Neo4j failure — caller must catch and fall back to in-memory.
    """
    store = GraphStore()
    try:
        driver = await store._get_driver()
        async with driver.session() as session:
            # Upsert nodes
            for f in findings:
                await session.run(
                    """
                    MERGE (n:OsFinding {id: $id})
                    SET n.vulnerability = $vulnerability,
                        n.severity = $severity,
                        n.chain_potential = $chain_potential
                    """,
                    id=f["id"],
                    vulnerability=f["vulnerability"],
                    severity=f["severity"],
                    chain_potential=f["chain_potential"],
                )
            # Upsert edges
            for src_id, dst_id in edges:
                await session.run(
                    """
                    MATCH (a:OsFinding {id: $src})
                    MATCH (b:OsFinding {id: $dst})
                    MERGE (a)-[:ENABLES]->(b)
                    """,
                    src=src_id,
                    dst=dst_id,
                )
            # Query paths of length 2-4
            result = await session.run(
                """
                MATCH path = (a:OsFinding)-[:ENABLES*2..4]->(b:OsFinding)
                RETURN [n IN nodes(path) | n.id] AS ids
                LIMIT 20
                """,
            )
            records = await result.data()
            return [list(r["ids"]) for r in records if r.get("ids")]
    finally:
        try:
            await store.close()
        except Exception:
            pass


# ── In-memory path enumeration ─────────────────────────────────────────────────

def _enumerate_paths_in_memory(
    findings: list[dict],
    edges: list[tuple[str, str]],
) -> list[list[str]]:
    """DFS over the adjacency list to enumerate simple paths of length 2-4
    (where length = number of edges, so 3-5 nodes inclusive). Returns up to
    _MAX_PATHS paths.
    """
    adjacency: dict[str, list[str]] = {f["id"]: [] for f in findings}
    for src, dst in edges:
        if src in adjacency:
            adjacency[src].append(dst)

    paths: list[list[str]] = []

    def dfs(current: str, trail: list[str]) -> None:
        if len(paths) >= _MAX_PATHS:
            return
        edge_count = len(trail) - 1
        if _MIN_HOPS <= edge_count <= _MAX_HOPS:
            paths.append(list(trail))
        if edge_count >= _MAX_HOPS:
            return
        for nxt in adjacency.get(current, []):
            if nxt in trail:  # avoid cycles — simple paths only
                continue
            trail.append(nxt)
            dfs(nxt, trail)
            trail.pop()
            if len(paths) >= _MAX_PATHS:
                return

    for node_id in adjacency:
        if len(paths) >= _MAX_PATHS:
            break
        dfs(node_id, [node_id])

    return paths


def _dedupe_paths(paths: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, ...]] = set()
    out: list[list[str]] = []
    for p in paths:
        key = tuple(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


# ── LLM response parsing ───────────────────────────────────────────────────────

def _parse_llm_chains(content: str) -> list[dict]:
    """Best-effort parser for the LLM's JSON-array response. Handles bare
    JSON, ```json``` fences, and plain ``` fences. Returns [] on failure.
    """
    raw = (content or "").strip()
    if raw.startswith("```"):
        # Strip the opening fence (possibly with language tag) and trailing fence.
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.exception("ChainDiscoveryAgent: could not parse LLM JSON response")
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("chains"), list):
        return parsed["chains"]
    return []
