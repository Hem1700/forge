# TrackedLLM Evolution & OS Scanning Pipeline

**Date:** 2026-05-20
**Status:** Design (awaiting implementation)
**Author:** Claude + Hem

---

## Overview

Two independent, high-value workstreams:

1. **TrackedLLM Evolution** — extend the LLM factory with cost enforcement, Redis-backed rate limiting, intelligent tier-based model routing, context window management, and semantic prompt caching. No new agent or pipeline code; all changes are inside `llm_factory.py` and supporting infrastructure.

2. **OS Scanning Pipeline** — a new engagement type (`os_ssh`, `os_agent`) that fingerprints a live Linux host over SSH, runs five purpose-built OS security agents in parallel, and synthesises multi-step attack chains using Neo4j. Reuses the entire existing finding/triage/report/WebSocket stack unchanged.

Both workstreams are independent and can be staffed in parallel or sequenced.

---

## Workstream 1: TrackedLLM Evolution

### Context

`TrackedLLM` (introduced in the multi-provider LLM sprint) wraps every LLM call to log token usage and cost to `llm_usage_events`. It currently does post-call accounting only. Five phases harden it into a production-grade gateway: budget enforcement, rate limiting, intelligent routing, context compression, and prompt caching.

All phases are backward-compatible — no calling code changes required outside `llm_factory.py` and new DB models.

---

### Phase 1 — Budget Enforcement

**Problem:** An org can burn unlimited API spend with no circuit breaker.

#### New DB model: `OrgBudget`

Table name: `org_budgets`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID, unique, indexed | FK → organizations.id |
| `monthly_limit_usd` | Numeric(12,4) | Monthly ceiling |
| `current_spend_usd` | Numeric(12,4), default 0 | Accumulated spend this period |
| `reset_day` | Integer (1–28) | Day of month to reset current_spend |
| `alert_threshold_pct` | Integer, default 80 | Emit warning event at this % of limit |
| `hard_cap` | Boolean, default True | True = block calls; False = warn only |
| `updated_at` | DateTime | |

**Alembic migration:** `create_table("org_budgets", ...)` — standalone migration, no changes to existing tables.

#### TrackedLLM changes

Before every LLM call:
1. Estimate call cost: `input_tokens_estimate * price_in + max_tokens * price_out` (use `max_tokens` from `LLMSpec` as worst-case output).
2. Query `OrgBudget` for `org_id`.
3. If `current_spend_usd + estimated_cost >= monthly_limit_usd`:
   - `hard_cap=True` → raise `BudgetExceededError("Monthly LLM budget exceeded")` — caught by API routes and surfaced as HTTP 402.
   - `hard_cap=False` → publish `budget_warning` WebSocket event; proceed with call.
4. At alert threshold (first time this period crossing `alert_threshold_pct`): publish `budget_alert` event regardless of hard_cap.

After every LLM call (in `TrackedLLM._log_usage`):
```sql
UPDATE org_budgets
SET current_spend_usd = current_spend_usd + :actual_cost
WHERE org_id = :org_id
```
Use a PostgreSQL advisory lock (`pg_advisory_xact_lock(hash(org_id))`) to prevent double-spend under parallel calls.

#### Monthly reset: Arq scheduled job

New function `reset_monthly_budgets` added to `worker.py`:
- Run daily at 00:05 UTC (cron-style via Arq's `cron` list).
- `UPDATE org_budgets SET current_spend_usd = 0 WHERE EXTRACT(DAY FROM NOW()) = reset_day`

#### REST endpoints

`GET /api/v1/org/budget` — returns current budget state (admin+).
`PUT /api/v1/org/budget` — create/update budget config (admin+). Body: `{monthly_limit_usd, reset_day, alert_threshold_pct, hard_cap}`.

Both endpoints go in `backend/app/api/org_llm.py` alongside existing credential/task-config endpoints.

#### New exception

`backend/app/brain/llm_factory.py`:
```python
class BudgetExceededError(Exception):
    """Raised when org's monthly LLM budget hard cap is reached."""
```

API catch in `backend/app/api/findings.py` and pipeline functions: `except BudgetExceededError → HTTPException(402, "Monthly LLM budget exceeded")`.

---

### Phase 2 — Per-Provider Rate Limiting in Redis

**Problem:** Under load (40 concurrent scans) all orgs share the same provider API keys; hitting provider rate limits cascades into Arq job timeouts.

#### Redis key schema

```
ratelimit:{org_id}:{provider}:tpm   → sorted set, member=timestamp_ns, score=timestamp_ms
ratelimit:{org_id}:{provider}:rpm   → sorted set, member=uuid, score=timestamp_ms
```

Sliding window via sorted sets:
- `ZREMRANGEBYSCORE key 0 (now_ms - window_ms)` — expire old entries
- `ZCARD key` — count entries in window
- `ZADD key score member` — record new entry

All three operations executed atomically via a Lua script to avoid TOCTOU races under concurrent calls.

TTL on each key: `window_ms + 60_000` ms (auto-expire if no traffic).

#### Default limits per provider (configurable per org)

| Provider | TPM | RPM |
|----------|-----|-----|
| Anthropic | 100,000 | 50 |
| OpenAI | 90,000 | 60 |
| Bedrock | 80,000 | 40 |
| Azure | 80,000 | 40 |
| Ollama | unlimited | unlimited |

#### New DB model: `OrgRateLimitConfig`

Table name: `org_rate_limit_configs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `org_id` | UUID, indexed | |
| `provider` | String(20) | enum value |
| `tpm_limit` | Integer, nullable | NULL = use default |
| `rpm_limit` | Integer, nullable | NULL = use default |

#### TrackedLLM changes

Before every call, after budget check:
1. Look up effective TPM/RPM limits (org override → provider default).
2. Run Lua script: check both windows. If either would be exceeded:
   - Sleep `asyncio.sleep(wait_ms / 1000)` with exponential backoff starting at 1s.
   - After 3 waits: raise `RateLimitQueuedError(retry_after_seconds=X)`.
3. Record the call in both windows (with estimated token count for TPM).
4. After call completes, update TPM window with actual token count (ZADD actual − estimated delta).

#### API surface

`RateLimitQueuedError` caught by API routes → HTTP 429 with `Retry-After: {seconds}` header.

No new REST endpoints needed (rate limit config managed via existing task-config pattern or new `OrgRateLimitConfig` admin endpoint if needed).

---

### Phase 3 — Intelligent Model Routing

**Problem:** Today all tasks default to Sonnet or Haiku as hardcoded in `DEFAULT_TASK_SPECS`. There's no principled mapping between task complexity and model tier; orgs pay Sonnet prices for tasks that Haiku handles equally well.

#### New enum: `TaskTier`

```python
class TaskTier(str, Enum):
    LIGHT    = "light"     # Fast, cheap: context building, summarization, recon
    STANDARD = "standard"  # Balanced: analysis, planning, classification
    HEAVY    = "heavy"     # Best model: exploit generation, judging, chain synthesis
```

#### `TASK_TIER_MAP`: 14 TaskType values → TaskTier

| TaskType | Tier | Rationale |
|----------|------|-----------|
| `codebase_modeling` | STANDARD | Structural analysis, not generative |
| `campaign_planning` | STANDARD | Planning; quality matters but not HEAVY |
| `code_analyzer` | STANDARD | Code pattern recognition |
| `semantic_modeler` | LIGHT | Classification / tagging |
| `findings_judge` | STANDARD | Needs accuracy; bulk volume |
| `execution_judge` | HEAVY | Security verdict; high stakes |
| `exploit_engine` | HEAVY | Generative; requires best reasoning |
| `exploit_script` | HEAVY | Generative; complex code |
| `poc_engine` | HEAVY | Generative; complex code |
| `evasion_strategist` | HEAVY | Adversarial; requires deep reasoning |
| `logic_modeler` | LIGHT | Structural extraction |
| `agent_brain` | STANDARD | Autonomous loop; balanced |
| `challenger` | STANDARD | Validation; accuracy matters |
| `severity_assessor` | LIGHT | Classification; well-bounded |

#### `TIER_MODEL_MAP`: per-provider, tier → model

| Provider | LIGHT | STANDARD | HEAVY |
|----------|-------|----------|-------|
| Anthropic | claude-haiku-4-5 | claude-sonnet-4-6 | claude-opus-4-7 |
| OpenAI | gpt-4o-mini | gpt-4o | o1 |
| Bedrock | anthropic.claude-haiku-4 | anthropic.claude-sonnet-4 | anthropic.claude-opus-4 |
| Azure | gpt-4o-mini | gpt-4-turbo | gpt-4o |

#### Resolution order in `_resolve_spec`

1. Explicit `OrgLLMTaskConfig` row for this `(org_id, task_type)` → use as-is (full override).
2. No row: look up `TASK_TIER_MAP[task]` → `TIER_MODEL_MAP[provider][tier]` using org's configured provider (or Anthropic default).
3. Fallback: existing `DEFAULT_TASK_SPECS[task]` (kept for backward compat with tests).

This change means orgs automatically get tier-appropriate models without any configuration, with the option to pin specific models via `OrgLLMTaskConfig`.

#### CLI command: `forge org llm tiers`

Output table:

```
╭─ Model Routing Table ─────────────────────────────────────────────────╮
│ Provider: anthropic                                                    │
│                                                                        │
│ Task                  Tier       Model              Source             │
│ codebase_modeling     standard   claude-sonnet-4-6  tier-default       │
│ exploit_engine        heavy      claude-opus-4-7    tier-default       │
│ findings_judge        standard   claude-sonnet-4-6  tier-default       │
│ semantic_modeler      light      claude-haiku-4-5   org-override       │
│ ...                                                                    │
╰────────────────────────────────────────────────────────────────────────╯
```

File: `cli/forge_cli/commands/org_llm.py`, new `tiers` subcommand under `forge org llm`.

---

### Phase 4 — Context Window Management

**Problem:** Long engagements accumulate large message histories. A 200KB context passed to Haiku (32K window) truncates silently; passed to Opus it costs $3/call.

#### New class: `ContextManager`

Location: `backend/app/brain/context_manager.py`

```python
class ContextManager:
    def prepare(self, messages: list, model: str) -> tuple[list, ContextStats]:
        ...
```

Algorithm:
1. **Count tokens**: use `tiktoken` for OpenAI models (`cl100k_base` encoding); use Anthropic's `client.count_tokens()` for Claude models. Token count is approximate (±5%) but sufficient for windowing decisions.
2. **Thresholds** (as % of model's context window):
   - `< 70%`: pass through unchanged.
   - `70–85%`: compress middle messages. Keep system prompt + first 2 messages + last 3 messages. Replace middle with a LIGHT-tier summarization call: `"Summarize these messages concisely, preserving all security findings, URLs, and technical details."` Cache the summary in Redis by `SHA256(middle_messages_text)` with TTL=1 hour.
   - `> 85%`: keep only system prompt + last 3 messages. Replace everything else with a compressed summary (same summarization call). Warn via log.
3. Return `(prepared_messages, ContextStats)`.

#### `ContextStats` dataclass

```python
@dataclass
class ContextStats:
    original_tokens: int
    final_tokens: int
    compression_applied: bool
    compression_savings_pct: float   # (original - final) / original
    model: str
```

`ContextStats` is appended to the `LLMUsageEvent.payload` JSON for observability.

#### Model context window registry

```python
_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-haiku-4-5":      200_000,
    "claude-sonnet-4-6":     200_000,
    "claude-opus-4-7":       200_000,
    "gpt-4o":                128_000,
    "gpt-4o-mini":           128_000,
    "gpt-4-turbo":           128_000,
    "o1":                    200_000,
    # Bedrock model IDs map to same windows as base models
}
```

#### Integration point

`TrackedLLM.ainvoke(messages)` calls `ContextManager.prepare(messages, self._model)` before passing to the underlying LLM. Compression calls are LIGHT-tier, use `get_llm(TaskType.semantic_modeler)` internally (avoids recursion via a direct LangChain call, bypassing TrackedLLM).

#### Redis key for compression cache

`ctx_compress:{SHA256(middle_messages_text)}` → compressed summary text, TTL 3600s.

---

### Phase 5 — Semantic Prompt Caching

**Problem:** Recurring scan types (e.g., `findings_judge` on the same vulnerability class) send identical or near-identical prompts. Each call costs tokens even when the response would be identical.

**Note:** Distinct from Anthropic's server-side prompt caching (which caches the KV state inside Claude). This is a client-side full-response cache for identical prompts.

#### Cache key

`SHA256(model + system_prompt_text + last_user_message_text)` → stored in Redis.

`last_user_message_text` is the final `HumanMessage.content` in the messages list. System prompt is the first `SystemMessage.content`.

#### Cache value

```json
{
  "content": "...",
  "input_tokens": 123,
  "output_tokens": 456,
  "cached_at": "2026-05-20T12:00:00Z"
}
```

#### TTL per task type

| Task | TTL | Rationale |
|------|-----|-----------|
| `semantic_modeler` | 24h | App type rarely changes |
| `findings_judge` | 4h | Triage verdicts stable within a day |
| `severity_assessor` | 4h | Same |
| `challenger` | 1h | May change with new evidence |
| `exploit_engine` | 0 | Never cache; each exploit is unique |
| `exploit_script` | 0 | Never cache |
| `poc_engine` | 0 | Never cache |
| `evasion_strategist` | 0 | Never cache |
| All others | 2h | Safe default |

#### On cache hit

1. Return cached response as a synthetic `AIMessage(content=cached["content"])`.
2. Log `LLMUsageEvent` with `cache_hit=True`, `cost_usd=0.0`, `input_tokens=cached["input_tokens"]`, `output_tokens=cached["output_tokens"]`.
3. Skip the actual LLM call, retry wrapper, and rate limit window recording.

#### Cache invalidation

Invalidate (DEL pattern `ctx_cache:{org_id}:*`) when:
- Org updates `OrgLLMTaskConfig` (provider/model change means cached responses may be wrong).
- Engagement is restarted (fresh context).

Cache key includes `org_id` prefix so per-org invalidation is scoped.

#### New CLI command: `forge org llm cache stats`

```
Cache entries:     142
Estimated savings: $4.23 this month
Hit rate:          34%
Oldest entry:      2h ago
```

Reads from Redis `SCAN` over `ctx_cache:{org_id}:*` keys.

---

### Scalability notes for TrackedLLM

| Concern | Solution |
|---------|---------|
| Budget double-spend under parallel calls | PostgreSQL advisory lock per `org_id` on budget update |
| Rate limit race under horizontal workers | Lua script for atomic sorted-set operations — Redis serialises them |
| Context compression adds latency | Compression is async, non-blocking; LIGHT-tier calls are fast (<500ms) |
| Cache key collisions | SHA256 is collision-resistant; key includes `model` so model upgrades auto-invalidate |
| Redis restart loses rate limit windows | Windows are short (1-min TPM, 1-min RPM); loss means a brief under-counting gap, not a security issue |
| Budget reset job misfire | Arq cron runs daily; if missed, next run catches up (idempotent WHERE clause) |

---

---

## Workstream 2: OS Scanning Pipeline

### Context

FORGE today targets web applications and local codebases. The most requested missing capability is Linux host assessment: privilege escalation paths, misconfigured services, vulnerable packages, and multi-step attack chains unique to a specific system's configuration. This workstream adds `os_ssh` and `os_agent` as first-class engagement types, reusing the entire existing pipeline/finding/triage/WebSocket infrastructure.

---

### Phase 1 — Target Model: OSModeler

Location: `backend/app/brain/os_modeler.py`

`OSModeler` connects to a target Linux host via SSH and collects a structured fingerprint using two modes.

#### Mode A: Agentless (SSH)

Uses `asyncssh` (pure-Python async SSH client; add to `requirements.txt`).

All commands run in a single multiplexed SSH connection (`asyncssh.connect()` with `known_hosts=None` for pentest targets). Commands execute in parallel via `asyncio.gather()`.

**Command set (read-only, no sudo required):**

| Output | Command |
|--------|---------|
| Kernel + distro | `uname -a && cat /etc/os-release` |
| Installed packages (Debian/Ubuntu) | `dpkg -l 2>/dev/null` |
| Installed packages (RHEL/CentOS/Fedora) | `rpm -qa 2>/dev/null` |
| Running processes | `ps auxf` |
| Open ports + owning processes | `ss -tlnup 2>/dev/null \|\| netstat -tlnup 2>/dev/null` |
| SUID/SGID binaries | `find / -perm -4000 -o -perm -2000 2>/dev/null \| head -500` |
| Users + groups | `cat /etc/passwd /etc/group` |
| Sudo rules | `cat /etc/sudoers /etc/sudoers.d/* 2>/dev/null` |
| Cron jobs | `cat /etc/crontab /etc/cron.d/* /var/spool/cron/* 2>/dev/null` |
| Kernel parameters | `sysctl -a 2>/dev/null` |
| Filesystem mounts | `cat /proc/mounts && df -h` |
| SSH config | `cat /etc/ssh/sshd_config 2>/dev/null` |
| PAM config | `cat /etc/pam.d/common-auth /etc/pam.d/sshd 2>/dev/null` |
| Writable paths | `find /tmp /var/tmp /dev/shm -writable 2>/dev/null && find / -writable -not -user $(whoami) 2>/dev/null \| head -100` |
| Login history | `last -n 50 && lastlog 2>/dev/null` |
| Enabled services | `systemctl list-units --type=service --state=running 2>/dev/null` |
| Network summary | `ss -s 2>/dev/null` |
| Environment of key processes | `cat /proc/1/environ 2>/dev/null \| tr '\\0' '\\n'` |

**Timeout per command:** 15s. Commands that time out or return a non-zero exit are silently skipped (partial fingerprints are acceptable).

**Total collection time target:** <30 seconds.

#### Mode B: Agent-based (Collector binary)

For deeper collection requiring elevated permissions.

**`forge-collector`** — lightweight Go binary:
- Location: `forge-collector/` directory at repo root.
- Compiled for `linux/amd64` and `linux/arm64` (cross-compile via `go build GOARCH=amd64 GOOS=linux`).
- Statically linked (`CGO_ENABLED=0`), no runtime dependencies.
- Deployed via SSH SCP, made executable, runs once, writes structured JSON to stdout, then self-deletes (`os.Remove(os.Args[0])`).
- If `--sudo` flag passed (and sudo granted): also reads `/etc/shadow` permissions, lists kernel modules (`lsmod`), reads capabilities of all processes (`/proc/{pid}/status` for `CapPrm`/`CapEff`).
- Output streamed line-by-line as newline-delimited JSON for easy async reading.

`OSModeler` detects which mode to use from `OSTarget.access_mode` field.

#### `OSFingerprint` output model

```python
@dataclass
class OSFingerprint:
    kernel: dict          # version, arch, build
    os: dict              # distro, version, id
    packages: list[dict]  # {name, version, arch, manager}
    processes: list[dict] # {pid, ppid, user, cmd, ports: list[int]}
    open_ports: list[dict]# {port, proto, process, user, bind_addr}
    suid_binaries: list[str]
    users: list[dict]     # {username, uid, gid, home, shell}
    groups: list[dict]    # {name, gid, members}
    sudo_rules: list[str] # raw lines from sudoers
    cron_jobs: list[dict] # {schedule, user, command, source_file}
    writable_paths: list[str]
    sysctl_params: dict   # key → value
    ssh_config: dict      # option → value
    pam_config: dict      # service → rules
    services: list[dict]  # {name, state, load_state, pid}
    mounts: list[dict]    # {device, mount_point, fstype, options}
    login_history: list[dict]
    collection_mode: str  # "agentless" | "collector"
    collected_at: str     # ISO datetime
```

`OSModeler.fingerprint(target: OSTarget) -> OSFingerprint`

---

### Phase 2 — New OS Agent Types

All OS agents extend `BaseAgent` (same dataclass pattern as existing agents). Each receives only the `OSFingerprint` slice relevant to its task — critical for token efficiency.

All agents are async, implement `_execute(task: Task) -> list[dict]` returning raw finding dicts.

#### Agent: `PrivescAgent`

Location: `backend/app/swarm/agents/privesc_agent.py`

**Input slice:** `suid_binaries, sudo_rules, writable_paths, cron_jobs, processes, users, groups`

**LLM task type:** `TaskType.privesc_analysis` (new — HEAVY tier, maps to Opus/GPT-o1)

**Check sequence (deterministic first, LLM second):**

1. **SUID/GTFOBins lookup** (no LLM):
   - Parse binary name from path.
   - Check `data/gtfobins.json` for SUID technique entry.
   - Finding if match found (confidence: 0.95 — deterministic).

2. **Sudo rules analysis** (LLM):
   - Extract rules with `NOPASSWD`, wildcard commands, dangerous binaries (vim, find, python, perl, ruby, awk, bash, sh, cp, mv, tee, etc.).
   - LLM prompt: "Given these sudo rules and system context, identify exploitable privilege escalation paths. For each path, provide: technique, command sequence, whether it requires user interaction, and GTFOBins reference if applicable."

3. **Writable cron paths** (deterministic):
   - Cross-reference: writable paths ∩ commands in cron jobs owned by root.
   - Finding if overlap found (confidence: 0.90).

4. **PATH hijacking** (deterministic):
   - Extract `PATH` from root's environment (via `/proc/1/environ`).
   - Check if any directory early in PATH is world-writable or user-writable.

5. **Docker escape vectors** (deterministic):
   - Check if current user is in `docker` group.
   - Finding if true (confidence: 0.85 — escalation to root via `docker run -v /:/mnt`).

6. **NFS no_root_squash** (deterministic):
   - Scan `mounts` for NFS entries with `no_root_squash` option.

**Output findings:** include `chain_potential: bool` flag. Set to `True` for any finding that could be a link in a multi-step chain (e.g., a SUID binary that doesn't directly give root but could be combined with a writable path).

#### Agent: `ServiceAuditAgent`

Location: `backend/app/swarm/agents/service_audit_agent.py`

**Input slice:** `services, open_ports, ssh_config, processes, packages`

**LLM task type:** `TaskType.service_audit` (new — STANDARD tier)

**Checks:**

1. **SSH hardening** (deterministic rules, no LLM):
   - `PermitRootLogin yes` → HIGH finding
   - `PasswordAuthentication yes` → MEDIUM finding
   - Weak ciphers: any of `3des-cbc, aes128-cbc, aes192-cbc, aes256-cbc` → MEDIUM
   - Weak MACs: any `md5` or `sha1` variant → MEDIUM
   - Weak KEX: `diffie-hellman-group1-sha1`, `diffie-hellman-group14-sha1` → MEDIUM

2. **Services running as root** (deterministic):
   - Cross-reference `processes` (user=root) with `open_ports` (process name).
   - Services that should never run as root: nginx, apache2, httpd, node, python, ruby.
   - Finding if match found.

3. **Unencrypted protocols** (deterministic):
   - Open ports: 23 (telnet), 21 (ftp), 513 (rsh), 514 (rlogin), 512 (rexec) on non-loopback → HIGH.

4. **Service version CVE lookup** (NVD cache, no LLM):
   - Extract service name + version from `packages` or banner grabs.
   - SQL lookup against `cve_cache` table.
   - Finding per CVE with CVSS ≥ 7.0.

5. **Exposed management interfaces** (deterministic):
   - Open ports on 0.0.0.0: 6379 (Redis), 5432 (Postgres), 11211 (Memcached), 27017 (MongoDB), 9200 (Elasticsearch).
   - Finding if no auth configured (inferred from process cmd flags).

#### Agent: `PackageVulnAgent`

Location: `backend/app/swarm/agents/package_vuln_agent.py`

**Input slice:** `packages, kernel` (kernel version for kernel CVEs)

**LLM task type:** `TaskType.package_vuln_analysis` (new — STANDARD tier, bulk; switch to LIGHT for triage)

**Architecture:**

1. **Trivy integration** (no LLM):
   - `trivy fs --format json --skip-db-update /dev/stdin` (pipe package list as synthetic filesystem).
   - Alternatively: direct query against local Trivy vulnerability DB (SQLite at `~/.cache/trivy/db/`).
   - Arq scheduled job (`refresh_trivy_db`, daily at 03:00 UTC) runs `trivy image --download-db-only`.
   - Output: list of `{package, installed_version, vuln_id, fixed_version, severity, cvss_score}`.

2. **CVE deduplication** (PostgreSQL cache):
   - `cve_cache` table (see Phase 4 for full schema).
   - Before calling Trivy for a package, check cache. Cache TTL: 24h.
   - Avoids re-running Trivy on every scan for the same package set.

3. **Exploitability-in-context** (LLM, STANDARD tier):
   - For CVEs with CVSS ≥ 6.0 only (skip low/info noise).
   - Batch: send up to 10 CVEs per LLM call.
   - Prompt: "Given these CVEs and the following system context [fingerprint summary], for each CVE assess: (1) Is the affected package actually used/exposed? (2) Does the system configuration make exploitation easier or harder? (3) Assign an adjusted exploitability score 0–1. Output JSON array."
   - Store `exploitability_in_context` score in finding's `evidence` field.

4. **Kernel CVEs:** treat kernel version as a package (`linux-kernel {version}`), same Trivy lookup.

#### Agent: `ConfigAuditAgent` (OS-extended version)

Location: `backend/app/swarm/agents/config_audit_agent.py` (extends existing codebase version)

**Input slice:** `sysctl_params, pam_config, ssh_config, users, mounts, services`

**LLM task type:** `TaskType.config_audit` (reuse existing — STANDARD tier)

**OS-specific checks (deterministic):**

| Check | Condition | Severity |
|-------|-----------|---------|
| ASLR disabled | `kernel.randomize_va_space != 2` | HIGH |
| Core dumps enabled for SUID | `fs.suid_dumpable != 0` | MEDIUM |
| ptrace unrestricted | `kernel.yama.ptrace_scope == 0` | MEDIUM |
| IP forwarding enabled | `net.ipv4.ip_forward == 1` (unexpected) | MEDIUM |
| ICMP redirects accepted | `net.ipv4.conf.all.accept_redirects == 1` | LOW |
| SYN cookies disabled | `net.ipv4.tcp_syncookies == 0` | MEDIUM |
| World-readable /etc/shadow | Detected via collector binary | CRITICAL |
| PAM no lockout policy | No `pam_faillock` or `pam_tally` in `/etc/pam.d/common-auth` | HIGH |
| /tmp mounted without noexec | `mounts` check | MEDIUM |
| NFS no_root_squash | `mounts` check | HIGH |

#### Agent: `NetworkExposureAgent`

Location: `backend/app/swarm/agents/network_exposure_agent.py`

**Input slice:** `open_ports, processes, mounts, sysctl` (net.* keys only)

**LLM task type:** `TaskType.network_exposure` (new — STANDARD tier)

**Checks:**

1. **External exposure matrix** (deterministic):
   - Build table: `{service, port, bind_addr, user}`.
   - Finding for each service binding on `0.0.0.0` or `::` that is also running as root.

2. **IPv6 exposure** (deterministic):
   - Scan `open_ports` for IPv6 (`::`) bindings where the equivalent IPv4 port is `127.0.0.1`.
   - Finding: "Service accessible via IPv6 but not IPv4 — firewall rules may not cover IPv6."

3. **Firewall vs reality discrepancy** (LLM):
   - If `iptables` rules collected (via collector binary), compare accepted ports against `open_ports`.
   - LLM prompt: "Compare these iptables rules with the actual listening ports. Identify discrepancies where a port is listening but not explicitly allowed or denied in iptables."

4. **Cross-correlation: port + root + no-auth** (deterministic):
   - If service binds on 0.0.0.0, runs as root, AND is in the unauthenticated management list (Redis, Memcached, etc.) → CRITICAL finding.

#### Agent: `ChainDiscoveryAgent`

Location: `backend/app/swarm/agents/chain_discovery_agent.py`

**Input:** all findings from the other four OS agents (full list, not a fingerprint slice)

**LLM task type:** `TaskType.chain_discovery` (new — HEAVY tier, always Opus/o1 — this is the highest-value call in OS scanning)

**Architecture:**

1. **Graph construction** (Neo4j):
   - Each finding → Neo4j node `(:Finding {id, type, severity, component, chain_potential})`
   - Edges `(:Finding)-[:ENABLES]->(:Finding)` based on heuristic rules:
     - Writable file ∩ cron job → ENABLES privesc
     - Low-priv shell + SUID binary → ENABLES escalation
     - Service running as root + exploitable CVE → ENABLES RCE
     - Network exposure + unauthenticated service → ENABLES initial access
   - Query: `MATCH path = (a:Finding)-[:ENABLES*2..4]->(b:Finding) WHERE b.type='privesc' RETURN path ORDER BY length(path) DESC LIMIT 20`

2. **LLM chain synthesis** (HEAVY tier):
   - Pass top 20 graph paths + full finding details to LLM.
   - System prompt: "You are a senior red-team operator. Analyze these attack paths on a single Linux system. For each viable multi-step chain: describe each step an attacker would take, explain why the individual findings seem low-risk in isolation but dangerous in combination, assign overall severity (consider that any path to root = CRITICAL), and estimate time-to-exploit for a skilled attacker."
   - Output: list of "chain findings" with `finding_type: "chain"`, `component_finding_ids: [uuid, ...]`, `chain_steps: [{step, action, finding_id}]`.

3. **Synthetic chain findings** persisted to the `findings` table with:
   - `vulnerability_class: "attack_chain"`
   - `evidence: {chain_steps, component_findings, neo4j_path_query}`
   - `severity`: derived from chain outcome (root access = critical; lateral movement = high)
   - `finding_type: "chain"` (new field on Finding model)

**Why this matters:** ChainDiscoveryAgent surfaces vulnerabilities that have no CVE ID and would never appear in a conventional vulnerability scanner. A world-writable `/etc/cron.d/` + a SUID `vim` + a weak sudo rule might each be MEDIUM individually; combined they are a 3-step root escalation.

---

### Phase 3 — Engagement Model Extension

#### `target_type` enum extension

`backend/app/models/engagement.py` — `EngagementStatus` unchanged, add to target_type values:
- `os_ssh` — agentless SSH collection
- `os_agent` — SSH + collector binary

#### New DB model: `OSTarget`

Table name: `os_targets`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `engagement_id` | UUID, FK → engagements.id, CASCADE | |
| `host` | String(255) | IP or hostname |
| `port` | Integer, default 22 | SSH port |
| `username` | String(100) | SSH login user |
| `auth_type` | String(20) | `password`, `key`, `agent` |
| `encrypted_credential` | LargeBinary, nullable | Fernet-encrypted password or private key |
| `access_mode` | String(20), default `agentless` | `agentless` or `collector` |
| `collector_sudo` | Boolean, default False | Whether to pass `--sudo` to forge-collector |
| `fingerprint_json` | JSON, nullable | Stored `OSFingerprint` after collection |
| `collected_at` | DateTime, nullable | |

`OSTarget` added to `Engagement.cascade` relationships (same `ondelete="CASCADE"` pattern as Bug 3 fix).

#### CLI extension

```
forge run 10.0.0.1 --type os --user ubuntu --key ~/.ssh/id_rsa
forge run 10.0.0.1 --type os --user ubuntu --password
forge run 10.0.0.1 --type os --user ubuntu --key ~/.ssh/id_rsa --collector --sudo
```

Auto-detect: if target looks like an IP or hostname (no `http://`, not a filesystem path) → offer `os_ssh` as detected type.

Password prompts via `click.prompt(..., hide_input=True)`.

Credential stored encrypted in `OSTarget.encrypted_credential` (same Fernet key used for LLM credentials).

#### Pipeline function: `_run_os_pipeline`

Location: `backend/app/api/start.py` — same pattern as `_run_web_pipeline`.

```
1. Load OSTarget from DB
2. OSModeler.fingerprint(target) → OSFingerprint (30s)
3. Persist fingerprint to OSTarget.fingerprint_json
4. asyncio.gather(
     PrivescAgent._execute(),
     ServiceAuditAgent._execute(),
     PackageVulnAgent._execute(),
     ConfigAuditAgent._execute(),
     NetworkExposureAgent._execute(),
   )
5. _save_finding() for each result
6. ChainDiscoveryAgent._execute(all_findings) → chain findings
7. _save_finding() for chain findings
8. enqueue("judge_findings", ...) for all findings
```

Arq job name: `run_os_pipeline`. Added to `WorkerSettings.functions`.

---

### Phase 4 — GTFOBins + NVD Integration

#### GTFOBins database

**File:** `backend/data/gtfobins.json`

Schema:
```json
{
  "vim": {
    "suid": {
      "commands": ["./vim -c ':py import os; os.execl(\"/bin/sh\", \"sh\", \"-pc\", \"reset; exec sh -p\")'\n"],
      "notes": "If vim has the SUID bit set..."
    },
    "sudo": {
      "commands": ["sudo vim -c ':!/bin/sh'"],
      "notes": "Sudo vim drops to a shell..."
    }
  },
  "find": { ... },
  ...
}
```

Scraped from gtfobins.github.io and converted to JSON. Initial version: ~250 binaries.

**Arq scheduled job:** `refresh_gtfobins` — runs monthly (first of month, 02:00 UTC). Scrapes gtfobins.github.io, diffs against current JSON, commits updated file if changed (or writes to a `gtfobins_cache` table in DB for zero-downtime updates).

**Usage in PrivescAgent:** `O(1)` dict lookup — `gtfobins.get(binary_name)` — no LLM call for detection, only for exploitability reasoning in context.

#### NVD CVE Cache

**Table:** `cve_cache`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `cve_id` | String(20), unique | e.g., CVE-2024-1234 |
| `package_name` | String(200), indexed | |
| `affected_versions` | JSON | list of version range specs |
| `fixed_version` | String(100), nullable | |
| `cvss_score` | Float, nullable | |
| `cvss_vector` | String(100), nullable | |
| `description` | Text | |
| `published_at` | DateTime | |
| `fetched_at` | DateTime | TTL check |

**Arq scheduled job:** `refresh_nvd_cache` — runs daily at 03:30 UTC.
- Fetches last 24h of NVD modifications: `https://services.nvd.nist.gov/rest/json/cves/2.0?lastModStartDate=...`
- Upserts into `cve_cache`.
- No NVD API key needed for polling intervals ≥ 6 seconds (rate limit: 10 requests/60s unauthenticated).

**Query in PackageVulnAgent:**
```sql
SELECT * FROM cve_cache
WHERE package_name = :pkg
  AND :version = ANY(affected_versions_array)
  AND (cvss_score IS NULL OR cvss_score >= 4.0)
ORDER BY cvss_score DESC NULLS LAST
```

---

### Scalability design for OS scanning

| Dimension | Design decision |
|-----------|----------------|
| Single host | 1 Arq job, <5 min end-to-end (30s collection + 5 parallel agents + chain discovery) |
| Many hosts (OS campaign) | `OSCampaign` model (future): 1 engagement, N `OSTarget` rows, 1 Arq job per host, fan-in chain agent |
| SSH connection overhead | Single multiplexed asyncssh connection per host; all commands share one TCP connection |
| Token efficiency | Each agent receives only its fingerprint slice — PrivescAgent never sees package list; PackageVulnAgent never sees sysctl |
| ChainDiscoveryAgent cost | One HEAVY-tier call per engagement; justified by finding quality (novel chains = highest value) |
| Collector binary size | <2MB statically linked Go binary; SCP transfer ~1s on LAN |
| Trivy DB size | ~200MB SQLite; cached locally; daily refresh via Arq |
| GTFOBins lookup | In-memory dict after load; 0ms lookup per binary |
| NVD cache hit rate | ~90% after first full sync (most packages unchanged day-to-day) |

#### Cross-host chain discovery (OSCampaign, future)

An `OSCampaign` engagement with multiple `OSTarget` rows enables lateral-movement chain discovery:
- Each host gets its own OS pipeline run.
- A campaign-level `LateralMovementAgent` receives all findings from all hosts.
- LLM prompt: "Given findings from these N hosts in the same network, identify lateral movement paths: e.g., credentials reused across hosts, shared SUID binaries, a pivot from a low-value host to a high-value host."
- Out of scope for this spec (future workstream), but OSTarget + OSCampaign models are designed to support it.

---

## New TaskType values (summary)

Phase 3 (routing) and OS agents introduce new `TaskType` entries. Full updated enum:

**Existing (14):** `codebase_modeling`, `campaign_planning`, `code_analyzer`, `semantic_modeler`, `findings_judge`, `execution_judge`, `exploit_engine`, `exploit_script`, `poc_engine`, `evasion_strategist`, `logic_modeler`, `agent_brain`, `challenger`, `severity_assessor`

**New (6):** `privesc_analysis` (HEAVY), `service_audit` (STANDARD), `package_vuln_analysis` (STANDARD), `config_audit` (STANDARD, already exists but extended), `network_exposure` (STANDARD), `chain_discovery` (HEAVY)

---

## New DB models (summary)

| Model | Table | Workstream |
|-------|-------|-----------|
| `OrgBudget` | `org_budgets` | TrackedLLM Phase 1 |
| `OrgRateLimitConfig` | `org_rate_limit_configs` | TrackedLLM Phase 2 |
| `OSTarget` | `os_targets` | OS Scanning Phase 3 |
| `CVECache` | `cve_cache` | OS Scanning Phase 4 |

Each requires a standalone Alembic migration (no changes to existing tables except `OrgBudget` requires adding `finding_type` column to `findings` for chain findings).

---

## New Arq scheduled jobs (summary)

| Job | Schedule | Workstream |
|-----|----------|-----------|
| `reset_monthly_budgets` | Daily 00:05 UTC | TrackedLLM Phase 1 |
| `refresh_trivy_db` | Daily 03:00 UTC | OS Phase 2 (PackageVulnAgent) |
| `refresh_nvd_cache` | Daily 03:30 UTC | OS Phase 4 |
| `refresh_gtfobins` | Monthly day 1, 02:00 UTC | OS Phase 4 |

---

## New Python dependencies

```
# TrackedLLM Evolution
tiktoken>=0.7         # token counting (OpenAI encoding)
# asyncssh already in use or add:
asyncssh>=2.14        # OS scanning SSH

# OS Scanning
asyncssh>=2.14
```

**Go dependency (collector binary):** no Python change; Go toolchain only needed when building `forge-collector`.

---

## Implementation order

### TrackedLLM (6 sprints, ~6 weeks)

| Sprint | Deliverable | ROI |
|--------|-------------|-----|
| 1 | Phase 1: Budget enforcement | Prevents runaway cost; sellable feature |
| 2 | Phase 2: Rate limiting in Redis | Prevents 429 cascades under load |
| 3 | Phase 3: Tier-based model routing | Immediate 30–50% cost reduction |
| 4–5 | Phase 4: Context window management | Prevents silent truncation at scale |
| 6 | Phase 5: Semantic prompt caching | 20–40% cost reduction on repeat scans |

### OS Scanning (9 sprints, ~9 weeks)

| Sprint | Deliverable |
|--------|-------------|
| 1 | OSModeler + asyncssh collection (agentless mode) |
| 2 | OSTarget model, `os_ssh` engagement type, CLI extension, `_run_os_pipeline` |
| 3 | PrivescAgent + GTFOBins DB (embedded JSON + Arq monthly refresh) |
| 4 | ServiceAuditAgent + ConfigAuditAgent (OS checks) |
| 5 | PackageVulnAgent + NVD cache + Trivy integration |
| 6 | NetworkExposureAgent |
| 7–8 | ChainDiscoveryAgent + Neo4j graph construction + LLM chain synthesis |
| 9 | Collector binary (`forge-collector` in Go) + `os_agent` mode |

**OS sprints 3–6 can run in parallel** if multiple engineers available — each agent is independent.

---

## Non-goals (this spec)

- Windows host scanning (future workstream).
- Cloud asset enumeration (AWS/GCP/Azure IAM, security groups) — separate spec.
- Web application scanning improvements — separate spec.
- Active exploitation (this pipeline is read-only collection + analysis; no payloads sent to target).
- Authenticated web scanning via harvested OS credentials (future cross-pipeline feature).
- SQLite or MySQL support for new tables — Postgres only, consistent with existing deployment.
