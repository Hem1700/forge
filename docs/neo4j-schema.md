# FORGE — Neo4j Graph Schema

FORGE uses Neo4j for two distinct graph workloads that differ in lifecycle and purpose.

---

## 1. Technique Knowledge Graph

**Scope:** Global, cross-engagement. Nodes persist indefinitely and accumulate knowledge from every scan.

### Node: `:Technique`

| Property | Type | Role |
|---|---|---|
| `technique_id` | `string` | Primary key (MERGE key) |
| `name` | `string` | Human-readable technique name |
| `attack_class` | `string` | Attack category (e.g. `sqli`, `privesc`, `xss`) |
| `tech_stack` | `list[string]` | Technology tags (e.g. `["python", "django"]`) |
| `outcome` | `string` | Expected result of exploiting this technique |

### Relationships

Both relationship types connect one `:Technique` to another and share the same signature:

```
(Technique)-[:LEADS_TO]->(Technique)
(Technique)-[:ENABLES]->(Technique)
```

`LEADS_TO` is the default relationship type used by `link_techniques()`. `ENABLES` can be specified explicitly via the `relationship` parameter when calling the same function.

### Cypher Examples

**Shortest path between two techniques:**

```cypher
MATCH path = shortestPath(
  (a:Technique {technique_id: $from_id})-[*]->(b:Technique {technique_id: $to_id})
)
RETURN [node in nodes(path) | node.technique_id] AS chain
```

**Get all techniques by attack class:**

```cypher
MATCH (t:Technique {attack_class: $attack_class}) RETURN t
```

### Populated by

| Function | Action |
|---|---|
| `knowledge/graph_store.py::GraphStore.upsert_technique()` | Creates or updates a `:Technique` node (MERGE on `technique_id`, SET remaining properties) |
| `knowledge/graph_store.py::GraphStore.link_techniques()` | Creates a `LEADS_TO` or `ENABLES` edge between two existing `:Technique` nodes |

### Queried by

| Function | Query |
|---|---|
| `knowledge/graph_store.py::GraphStore.shortest_path()` | `shortestPath()` between two techniques — returns ordered list of `technique_id` strings |
| `knowledge/graph_store.py::GraphStore.get_chains_for_class()` | Fetch all techniques matching a given `attack_class` |

---

## 2. OsFinding Engagement Graph

**Scope:** Per-scan, ephemeral. Nodes are written with UUID identifiers generated at scan time and are not cleaned up automatically between scans (nodes accumulate per Neo4j session).

### Node: `:OsFinding`

| Property | Type | Notes |
|---|---|---|
| `id` | `string` (UUID) | Primary key (MERGE key); generated with `uuid.uuid4()` at agent runtime — not stored in PostgreSQL |
| `vulnerability` | `string` | Vulnerability type slug (e.g. `writable_cron_path`, `suid_gtfobins`) |
| `severity` | `string` | Normalised lowercase severity: `critical`, `high`, `medium`, `low`, `informational` |
| `chain_potential` | `boolean` | True when the finding's source agent flagged it as a potential chain component |

### Relationships

```
(OsFinding)-[:ENABLES]->(OsFinding)
```

Edges are created by `_build_edges()` in `chain_discovery_agent.py` using six deterministic heuristic rules:

| From `vulnerability` | To `vulnerability` | Condition |
|---|---|---|
| `writable_cron_path` | `suid_gtfobins` | — (unconditional) |
| `writable_cron_path` | `docker_group_privesc` | — (unconditional) |
| `root_service_exposed` | `known_cve` | destination severity is `critical` or `high` |
| `network_exposure_bypass` | `root_service_exposed` | — (unconditional) |
| `unauthenticated_root_service` | `docker_group_privesc` | — (unconditional) |
| any `chain_potential=True` | any other `chain_potential=True` | at least one of the pair has severity `critical` or `high` |

### Cypher Path Query

The following query is issued after nodes and edges are written; it returns all 2-to-4-hop chains (up to 20 results):

```cypher
MATCH path = (a:OsFinding)-[:ENABLES*2..4]->(b:OsFinding)
RETURN [n IN nodes(path) | n.id] AS ids
LIMIT 20
```

Each result row is a list of finding UUID strings representing one attack chain candidate.

### Populated by

`swarm/agents/chain_discovery_agent.py::_persist_and_query_neo4j()` — writes `:OsFinding` nodes via MERGE and then creates `:ENABLES` edges before issuing the path query above, all within a single driver session.

### Fallback

When Neo4j is unavailable, `_enumerate_paths_in_memory()` performs a DFS over the same adjacency list built by `_build_edges()`. It enumerates simple paths of length 2-4 edges (3-5 nodes inclusive) and caps output at 20 paths. The two result sets are merged and deduplicated before being passed to the LLM for narrative synthesis.

---

## Connection Configuration

| Setting | Default | Environment Variable |
|---|---|---|
| URL | `bolt://localhost:17687` | `NEO4J_URL` |
| User | `neo4j` | `NEO4J_USER` |
| Password | `forge_password` | `NEO4J_PASSWORD` |

The defaults are read from `app/config.py::Settings` (via `pydantic-settings`; values can be overridden in `.env`).

**Docker Compose port remapping:** the FORGE `docker-compose.yml` maps Neo4j's internal Bolt port `7687` to `17687` on the host, and the browser port `7474` to `17474`. Always use `bolt://localhost:17687` (not `7687`) when connecting from outside the Compose network.
