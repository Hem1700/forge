# Multi-Provider LLM & Portable Database Design

**Date:** 2026-05-17
**Status:** Design (awaiting user review)
**Author:** Claude + Hem (brainstormed via `superpowers:brainstorming`)

## Problem

Today FORGE is hardcoded to two opinionated choices:

1. **LLM:** 14 separate `ChatAnthropic(model="claude-sonnet-4-6", api_key=settings.anthropic_api_key, max_tokens=N)` instantiations across `app/brain/` and `app/swarm/agents/`. Model name and provider are baked into every brain module. No path for an org to bring its own key, choose OpenAI, run on Bedrock, or use a cheaper model for triage tasks.
2. **DB:** PostgreSQL-only via SQLAlchemy + asyncpg. Models import `from sqlalchemy.dialects.postgresql import UUID`. No tested path to MySQL/MariaDB even though most enterprise customers run one of those.

Both are install-time blockers for prospective customers with provider preferences, compliance requirements, or cost ceilings.

## Goals

- An org admin can pick any of **Anthropic / OpenAI / Bedrock / Azure OpenAI** as their LLM provider, paste their own key, and have all agents in their org's engagements use it.
- An org admin can choose a different model per brain task (e.g., Sonnet for codebase modeling, Haiku for triage). Presets (Smart / Balanced / Cheap) hide this complexity for typical users.
- The operator can deploy FORGE on **Postgres or MySQL/MariaDB** by setting `DB_URL`.
- Existing single-tenant deployments using `ANTHROPIC_API_KEY` env var keep working with zero migration.
- Token usage and approximate cost are tracked per-org / per-engagement / per-task for billing and audit.

## Non-goals (deferred)

- Per-org database. DB is per-deployment, not per-org.
- Local LLMs (Ollama, vLLM) and exotic providers (Vertex AI, Cohere, Together, etc.). Big-3 first; add later behind the same factory if there's demand.
- True secret-manager integration (Vault, AWS Secrets Manager). Encrypted-in-Postgres only for v1.
- SQLite support. Out of scope for "production database" claims.
- Multi-region failover or active load balancing across providers.

## Design

### Scope decisions (resolved during brainstorming)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Config scope | **Per-deployment for DB, per-org for LLM** | DB is infrastructure; LLM is org policy (cost / privacy / compliance varies per customer). |
| LLM providers | **Anthropic, OpenAI, Bedrock, Azure OpenAI** | Covers ~90% of enterprise need. Avoids LiteLLM proxy concept and 100-provider sprawl. |
| Model granularity | **Per task type** (14 task types) | Lets orgs assign cheap models to triage and smart models to deep reasoning. Presets keep UX simple. |
| Key storage | **Encrypted column in Postgres (Fernet, master key from env)** | Self-contained; no extra infra. Multi-tenant prod can layer in a secret manager later behind the same API. |
| Fallback when org unconfigured | **Deployment-level default env vars** | Zero-friction migration. Existing `ANTHROPIC_API_KEY` keeps working. |
| Supported DBs | **Postgres + MySQL/MariaDB** | Two real production targets. SQLite excluded — sufficient for tests via Postgres in CI. |
| Bedrock auth | **Static keys + IAM role (instance metadata)** | Most AWS-shop customers run on EC2/ECS and prefer IAM role assumption over static keys. |
| Rate-limit / 429 behavior | **Exponential backoff (3 retries), then fail loudly** | Don't silently fall back to deployment defaults (would mask budget bugs); don't fail on first 429 (transient). |
| Test mocking | **Factory level** | Patch `get_llm` once per test instead of patching `ainvoke` on every brain module. |

### Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                       Brain Modules (14 sites)                      │
│  codebase_modeler · campaign_planner · code_analyzer · etc.        │
│                                                                    │
│  Old: ChatAnthropic(model="claude-sonnet-4-6", api_key=...)        │
│  New: await get_llm(TaskType.codebase_modeling, org_id=...)        │
└────────────────────────────┬───────────────────────────────────────┘
                             │ TaskType + org_id
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                    app/brain/llm_factory.py                        │
│                                                                    │
│  get_llm(task, org_id, engagement_id):                             │
│    1. resolve_spec(task, org) → LLMSpec(provider, model, params)   │
│    2. resolve_credentials(provider, org) → ProviderCreds           │
│    3. build LangChain BaseChatModel via _BUILDERS[provider]        │
│    4. wrap in TrackedLLM(usage logging) + RetryLLM(backoff)        │
│    5. return                                                       │
└────┬─────────────────┬──────────────────┬──────────────────┬───────┘
     │                 │                  │                  │
     ▼                 ▼                  ▼                  ▼
┌──────────┐    ┌──────────────┐   ┌──────────────────┐  ┌────────────┐
│ Anthropic│    │   OpenAI     │   │ Bedrock          │  │ Azure OAI  │
│ via      │    │   via        │   │ static + IAM     │  │ via        │
│ langchain│    │ langchain    │   │ langchain_aws    │  │ langchain  │
│_anthropic│    │_openai       │   │                  │  │_openai     │
└──────────┘    └──────────────┘   └──────────────────┘  └────────────┘
```

### Core types

```python
# app/brain/llm_factory.py
from enum import Enum
from pydantic import BaseModel

class TaskType(str, Enum):
    codebase_modeling   = "codebase_modeling"
    campaign_planning   = "campaign_planning"
    code_analyzer       = "code_analyzer"
    semantic_modeler    = "semantic_modeler"
    findings_judge      = "findings_judge"
    execution_judge     = "execution_judge"
    exploit_engine      = "exploit_engine"
    exploit_script      = "exploit_script"
    poc_engine          = "poc_engine"
    evasion_strategist  = "evasion_strategist"
    logic_modeler       = "logic_modeler"
    agent_brain         = "agent_brain"
    challenger          = "challenger"
    severity_assessor   = "severity_assessor"

class Provider(str, Enum):
    anthropic = "anthropic"
    openai    = "openai"
    bedrock   = "bedrock"
    azure     = "azure"

class LLMSpec(BaseModel):
    provider: Provider
    model: str
    max_tokens: int = 4000
    temperature: float = 0.0

class ProviderCreds(BaseModel):
    provider: Provider
    api_key: str | None = None
    region: str | None = None            # Bedrock
    endpoint: str | None = None          # Azure
    use_iam_role: bool = False           # Bedrock
    extra: dict = {}

async def get_llm(
    task: TaskType,
    org_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
) -> "TrackedLLM":
    ...
```

### Defaults table

A single source of truth for "what model handles what task" when an org hasn't overridden. Tuned for the Balanced preset:

```python
DEFAULT_TASK_SPECS: dict[TaskType, LLMSpec] = {
    # Heavy reasoning — needs a smart model
    TaskType.codebase_modeling:  LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=8000),
    TaskType.code_analyzer:      LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.exploit_engine:     LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=6000),
    TaskType.exploit_script:     LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.poc_engine:         LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.agent_brain:        LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.semantic_modeler:   LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.campaign_planning:  LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.evasion_strategist: LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=3500),
    TaskType.logic_modeler:      LLMSpec(provider="anthropic", model="claude-sonnet-4-6", max_tokens=2000),
    # Fast triage / judging — Haiku
    TaskType.findings_judge:     LLMSpec(provider="anthropic", model="claude-haiku-4-5", max_tokens=2500),
    TaskType.execution_judge:    LLMSpec(provider="anthropic", model="claude-haiku-4-5", max_tokens=2000),
    TaskType.severity_assessor:  LLMSpec(provider="anthropic", model="claude-haiku-4-5", max_tokens=500),
    TaskType.challenger:         LLMSpec(provider="anthropic", model="claude-haiku-4-5", max_tokens=500),
}
```

Presets are computed transformations of this table:

| Preset    | Transform                                                          |
|-----------|--------------------------------------------------------------------|
| Smart     | Every task → smart model of org's provider                         |
| Balanced  | Use `DEFAULT_TASK_SPECS` mapping (default)                         |
| Cheap     | Every task → cheap model of org's provider                         |
| Custom    | Org sets each row in `org_llm_task_config` independently           |

Provider-specific smart/cheap pairs:

| Provider  | Smart                | Cheap                     |
|-----------|----------------------|---------------------------|
| Anthropic | claude-sonnet-4-6    | claude-haiku-4-5          |
| OpenAI    | gpt-4-turbo          | gpt-4o-mini               |
| Bedrock   | anthropic.claude-sonnet-4 | anthropic.claude-haiku-4 |
| Azure     | (org's deployment name, defaulted to "gpt-4-turbo") | (org's deployment, "gpt-4o-mini") |

### Resolution flow

```python
async def get_llm(task, org_id, engagement_id):
    # 1. Spec resolution
    spec = await _resolve_spec(task, org_id)
    # 2. Credential resolution
    creds = await _resolve_credentials(spec.provider, org_id)
    # 3. Build raw LangChain client
    raw = _BUILDERS[spec.provider](spec, creds)
    # 4. Wrap for retries
    retrying = RetryLLM(raw, retries=3, backoff_base=1.0)
    # 5. Wrap for usage tracking
    return TrackedLLM(retrying, task=task, org_id=org_id, engagement_id=engagement_id,
                      provider=spec.provider, model=spec.model)


async def _resolve_spec(task, org_id) -> LLMSpec:
    if org_id:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgLLMTaskConfig).where(
                    OrgLLMTaskConfig.org_id == org_id,
                    OrgLLMTaskConfig.task_type == task.value,
                )
            )).scalar_one_or_none()
            if row:
                return LLMSpec(
                    provider=row.provider,
                    model=row.model,
                    max_tokens=row.max_tokens or DEFAULT_TASK_SPECS[task].max_tokens,
                    temperature=row.temperature or 0.0,
                )
    return DEFAULT_TASK_SPECS[task]


async def _resolve_credentials(provider, org_id) -> ProviderCreds:
    if org_id:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgLLMCredential).where(
                    OrgLLMCredential.org_id == org_id,
                    OrgLLMCredential.provider == provider.value,
                )
            )).scalar_one_or_none()
            if row:
                return ProviderCreds(
                    provider=provider,
                    api_key=_fernet.decrypt(row.encrypted_key).decode() if row.encrypted_key else None,
                    region=row.region,
                    endpoint=row.endpoint,
                    use_iam_role=row.extra.get("use_iam_role", False),
                    extra=row.extra,
                )
    # Fall back to deployment env
    return _ENV_CREDS[provider]
```

### Retry wrapper

```python
class RetryLLM:
    def __init__(self, llm, retries=3, backoff_base=1.0):
        self.llm = llm
        self.retries = retries
        self.backoff_base = backoff_base

    async def ainvoke(self, messages, **kw):
        for attempt in range(self.retries + 1):
            try:
                return await self.llm.ainvoke(messages, **kw)
            except RateLimitError as e:
                if attempt == self.retries:
                    raise
                wait = self.backoff_base * (2 ** attempt)  # 1s, 2s, 4s
                logger.warning("LLM rate-limited, retrying in %ss (attempt %d/%d)", wait, attempt+1, self.retries)
                await asyncio.sleep(wait)
```

Provider-specific exceptions are caught and normalized (`anthropic.RateLimitError`, `openai.RateLimitError`, etc.).

### Cost tracking

```python
class TrackedLLM:
    def __init__(self, llm, task, org_id, engagement_id, provider, model):
        ...

    async def ainvoke(self, messages, **kw):
        t0 = time.monotonic()
        response = await self.llm.ainvoke(messages, **kw)
        usage = getattr(response, "usage_metadata", {}) or {}
        await _log_usage(
            org_id=self.org_id,
            engagement_id=self.engagement_id,
            task=self.task.value,
            provider=self.provider.value,
            model=self.model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=_price(self.provider, self.model, usage),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        return response
```

Pricing table baked into code:

```python
# USD per 1M tokens (input, output)
_PRICING: dict[tuple[Provider, str], tuple[float, float]] = {
    (Provider.anthropic, "claude-sonnet-4-6"): (3.0, 15.0),
    (Provider.anthropic, "claude-haiku-4-5"):  (0.25, 1.25),
    (Provider.openai,    "gpt-4-turbo"):       (10.0, 30.0),
    (Provider.openai,    "gpt-4o-mini"):       (0.15, 0.6),
    # ... etc; missing entries log cost=0 rather than crash
}
```

### Database schema

```sql
-- ─────────────────────────────────────────────────────────────────────
-- Credentials per org, one row per (org, provider)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE org_llm_credentials (
    id            UUID PRIMARY KEY,
    org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    provider      VARCHAR(20) NOT NULL,         -- anthropic | openai | bedrock | azure
    encrypted_key BLOB,                         -- Fernet ciphertext; NULL when use_iam_role=true
    region        VARCHAR(50),                  -- AWS region for Bedrock
    endpoint      VARCHAR(500),                 -- Azure endpoint URL
    extra         JSON DEFAULT '{}',            -- {"use_iam_role": true, ...}
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW(),
    UNIQUE (org_id, provider)
);

-- ─────────────────────────────────────────────────────────────────────
-- Per-task config; absent rows fall back to DEFAULT_TASK_SPECS
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE org_llm_task_config (
    id          UUID PRIMARY KEY,
    org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    task_type   VARCHAR(50) NOT NULL,
    provider    VARCHAR(20) NOT NULL,
    model       VARCHAR(100) NOT NULL,
    max_tokens  INT,                            -- NULL = use task default
    temperature FLOAT,
    updated_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (org_id, task_type)
);

-- ─────────────────────────────────────────────────────────────────────
-- Audit log; never stores the actual key, just what changed
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE org_llm_audit_log (
    id         UUID PRIMARY KEY,
    org_id     UUID NOT NULL REFERENCES organizations(id),
    user_id    UUID REFERENCES users(id),
    action     VARCHAR(30) NOT NULL,            -- set_key | rotate | revoke | set_task_config | test | apply_preset
    payload    JSON NOT NULL,                   -- {provider, task_type, model, ...}; NEVER the key
    created_at TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────
-- Usage events — one row per LLM call
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE llm_usage_events (
    id             BIGSERIAL PRIMARY KEY,
    org_id         UUID NOT NULL REFERENCES organizations(id),
    engagement_id  UUID REFERENCES engagements(id) ON DELETE SET NULL,
    task           VARCHAR(50) NOT NULL,
    provider       VARCHAR(20) NOT NULL,
    model          VARCHAR(100) NOT NULL,
    input_tokens   INT NOT NULL DEFAULT 0,
    output_tokens  INT NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(12, 6) NOT NULL DEFAULT 0,
    duration_ms    INT NOT NULL DEFAULT 0,
    created_at     TIMESTAMP DEFAULT NOW(),
    INDEX (org_id, created_at),
    INDEX (engagement_id)
);
```

All four tables are MySQL-portable (no Postgres-only types). `BIGSERIAL` becomes `BIGINT AUTO_INCREMENT` on MySQL via SQLAlchemy's portable `Integer + primary_key + autoincrement`.

### DB portability

**Type swaps across all existing models:**

```python
# Before (Postgres-only)
from sqlalchemy.dialects.postgresql import UUID
id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

# After (portable)
from sqlalchemy import Uuid
id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
```

`Uuid` (SQLAlchemy 2.x) renders as `UUID` on Postgres, `CHAR(32)` on MySQL — round-trips correctly in both directions.

**Driver dependency added to `backend/pyproject.toml`:**
```toml
asyncmy = "^0.2.10"  # MySQL/MariaDB async driver
```

**`DB_URL` env var** drives dialect selection in `app/database.py`. No code branches required.

**CI matrix** runs the full test suite against both Postgres and MySQL.

### REST API

All endpoints under `/api/v1/org/llm/`. `require_admin` dependency on all writes.

```
GET    /providers              → list supported providers + required fields per provider
GET    /credentials            → list configured providers (status only, never the key)
PUT    /credentials/{provider} → upsert credentials  body: {api_key, region?, endpoint?, use_iam_role?}
POST   /credentials/{provider}/test → 1-token probe; returns {ok: bool, error?: str}
DELETE /credentials/{provider} → revoke

GET    /task-config            → full TaskType → LLMSpec map (defaults filled in for missing rows)
PUT    /task-config            → bulk set  body: {preset: "smart"|"balanced"|"cheap"} OR {custom: {<task>: <spec>}}

GET    /usage?since=2026-05-01&group_by=task|engagement|day → aggregated usage
GET    /audit?limit=100        → audit log entries
```

Response examples:

```json
// GET /credentials
[
  {"provider": "anthropic", "configured": true,  "use_iam_role": false, "last_tested_at": "2026-05-17T12:00:00Z"},
  {"provider": "openai",    "configured": false},
  {"provider": "bedrock",   "configured": true,  "use_iam_role": true,  "region": "us-east-1"},
  {"provider": "azure",     "configured": false}
]

// GET /task-config
{
  "preset": "balanced",
  "tasks": {
    "codebase_modeling": {"provider": "anthropic", "model": "claude-sonnet-4-6", "max_tokens": 8000, "from_default": false},
    "findings_judge":    {"provider": "anthropic", "model": "claude-haiku-4-5",  "max_tokens": 2500, "from_default": true}
  }
}
```

### CLI

```
forge org llm preset smart | balanced | cheap
forge org llm set <task-type> --provider openai --model gpt-4-turbo [--max-tokens 4000]
forge org llm show                            # table of current task → provider/model
forge org llm key set <provider>              # prompts for key (hidden); --iam-role for bedrock
forge org llm key test <provider>             # validates key, prints ok/error
forge org llm key revoke <provider>
forge org llm usage [--since 7d] [--by task|engagement|day]
```

`forge org llm show` output sketch:
```
╭─ AI Provider Configuration (org: Acme Security) ─╮
│ Active credentials                                │
│   anthropic   ✓ configured · last tested 2h ago   │
│   bedrock     ✓ IAM role · us-east-1              │
│                                                   │
│ Preset: balanced                                  │
│                                                   │
│ Task                  Provider    Model           │
│ codebase_modeling     anthropic   sonnet-4-6      │
│ findings_judge        anthropic   haiku-4-5       │
│ ...                                               │
╰───────────────────────────────────────────────────╯
```

### Frontend

New route: `/settings/ai-providers` (admin+ only; viewer redirected).

**Layout:**

1. **Credentials section** — grid of 4 cards (one per provider). Each card shows:
   - Status badge: "Configured" / "Not configured"
   - Input field for new key (hidden) + Save
   - For Bedrock: toggle "Use IAM role (recommended)" hides key input
   - For Azure: extra endpoint URL input
   - "Test" button → calls `POST /credentials/{provider}/test`
   - "Revoke" link if configured

2. **Task configuration section** — radio: Smart / Balanced / Cheap / Custom
   - Custom expands into a 14-row table: each row = task type with provider+model dropdowns
   - "Apply" button → `PUT /task-config`

3. **Usage section** — recharts line chart, last 30 days, grouped by task
   - Total cost YTD card
   - Top 5 most-expensive engagements link list

### Test strategy

**Existing tests:** every brain module currently patches `_LLMWrapper.ainvoke` or similar. After refactor, those mocks shift to one place:

```python
@pytest.fixture
def mock_llm(monkeypatch):
    fake_response = AIMessage(content='{"app_type": "fastapi", ...}')
    async def fake_get_llm(*args, **kw):
        m = AsyncMock()
        m.ainvoke = AsyncMock(return_value=fake_response)
        return m
    monkeypatch.setattr("app.brain.llm_factory.get_llm", fake_get_llm)
    return fake_response
```

**New tests:**
- `test_llm_factory.py` — resolution logic with/without org overrides; credential decryption; provider builder branching; retry behavior under rate limit.
- `test_org_llm_endpoints.py` — endpoint auth, key never leaks in responses, audit log written on every write, test endpoint behavior.
- `test_db_portability.py` — runs schema migration and a smoke test against both Postgres and MySQL in CI matrix.

### Migration plan

1. **PR 1 — schema + factory skeleton** (no behavior change)
   - Alembic migration adds the 4 new tables.
   - `llm_factory.py` exists but isn't called anywhere yet. `get_llm` returns the same `ChatAnthropic` as today.
   - All tests still pass.

2. **PR 2 — refactor all 14 call sites** (no behavior change for default config)
   - Each brain module / agent / validator calls `await get_llm(TaskType.X, org_id=...)`.
   - Org context plumbed through: every entry point that creates a brain object receives `engagement.org_id` and passes it down.
   - Default behavior preserved for orgs without overrides.

3. **PR 3 — REST endpoints + CLI** (new admin surface)
   - Endpoints, encryption, audit log, test probe.
   - CLI commands.

4. **PR 4 — frontend** (admin UI)
   - "Settings → AI Providers" page with credentials + preset picker.

5. **PR 5 — cost tracking**
   - `TrackedLLM` wrapper, `llm_usage_events` table, `GET /usage` endpoint.
   - Frontend usage chart.

6. **PR 6 — DB portability**
   - Type swaps (`UUID` → `Uuid`).
   - Add `asyncmy` driver.
   - CI matrix for Postgres + MySQL.
   - README updates with both connection strings.

### Operator deployment

**`FORGE_SECRETS_KEY` env var required** for credential encryption. Generated once per deployment:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Backend refuses to start if `FORGE_SECRETS_KEY` is unset AND `ANTHROPIC_API_KEY` is unset (i.e., no LLM at all). If only env-key fallback is configured, secrets storage isn't reachable — backend logs a warning but boots.

**Env vars (full list after this work):**
- `DB_URL` — Postgres or MySQL connection string
- `REDIS_URL` — unchanged
- `FORGE_SECRETS_KEY` — Fernet master key (new)
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` / `AZURE_OPENAI_API_KEY` — deployment-level fallback keys (one or more)
- `JWT_SECRET` — unchanged

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Encrypted DB column with master key rotation is annoying | v1 doesn't support rotation. Doc the procedure: re-encrypt all rows with the new key on each rotation. v2 can add per-row key versioning if needed. |
| Bedrock IAM role auth requires AWS SDK behavior we don't fully control | Use `langchain_aws.ChatBedrock` which supports both modes via boto3 credential chain. |
| MySQL `Uuid` storage (`CHAR(32)`) sorts differently than Postgres native `UUID` | We never sort by ID in user-facing queries; only by `created_at`. Confirmed by grep. |
| Refactoring 14 call sites in one PR is risky | PR 2 done file-by-file with tests passing per commit. Each commit is reviewable. |
| Cost calculation drift as providers change prices | Pricing table is a single dict; bump version on price changes. Out-of-table models log cost=0 rather than failing. |
| Org admin pastes a typo'd key, breaks all engagements | "Test" button in UI calls the provider with a 1-token request before save. CLI `forge org llm key test` does the same. |

## Open questions for review

- **Should we also support per-engagement override?** E.g., a user starting an engagement could pick a different model for just that run. (My take: no, keep org-level only — adds UI complexity for marginal benefit.)
- **What happens if a deployment-default key is set AND an org has its own key?** Org's takes precedence (current spec). Alternative would be admin lock-out for compliance. Going with org-precedence.
- **Should we expose model temperature in the UI?** v1: no, hide it (advanced users use CLI). UI surface: provider + model + max_tokens only.

## Estimate

5–6 days of focused work split across 6 PRs (see Migration plan).
