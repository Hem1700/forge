# backend/app/brain/llm_factory.py
"""LLM factory — resolves provider/model per org, wraps for retry and usage tracking."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from enum import Enum

from cryptography.fernet import Fernet
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


# ── Enums and types ───────────────────────────────────────────────────────────

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
    # OS scanning agents
    privesc_analysis      = "privesc_analysis"
    service_audit         = "service_audit"
    package_vuln_analysis = "package_vuln_analysis"
    config_audit          = "config_audit"
    network_exposure      = "network_exposure"
    chain_discovery       = "chain_discovery"


class Provider(str, Enum):
    anthropic = "anthropic"
    openai    = "openai"
    bedrock   = "bedrock"
    azure     = "azure"


class TaskTier(str, Enum):
    LIGHT    = "light"
    STANDARD = "standard"
    HEAVY    = "heavy"


class LLMSpec(BaseModel):
    provider: Provider
    model: str
    max_tokens: int = 4000
    temperature: float = 0.0


class ProviderCreds(BaseModel):
    provider: Provider
    api_key: str | None = None
    region: str | None = None
    endpoint: str | None = None
    use_iam_role: bool = False
    extra: dict = {}


# ── Default task → spec mapping (Balanced preset) ────────────────────────────

DEFAULT_TASK_SPECS: dict[TaskType, LLMSpec] = {
    TaskType.codebase_modeling:  LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=8000),
    TaskType.code_analyzer:      LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.exploit_engine:     LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=6000),
    TaskType.exploit_script:     LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.poc_engine:         LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.agent_brain:        LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.semantic_modeler:   LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.campaign_planning:  LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.evasion_strategist: LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3500),
    TaskType.logic_modeler:      LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=2000),
    TaskType.findings_judge:     LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=2500),
    TaskType.execution_judge:    LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=2000),
    TaskType.severity_assessor:  LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=500),
    TaskType.challenger:         LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=500),
    TaskType.privesc_analysis:      LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.service_audit:         LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.package_vuln_analysis: LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.config_audit:          LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.network_exposure:      LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.chain_discovery:       LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=8000),
}

# Smart/cheap model pairs per provider (for preset application)
_SMART_MODELS: dict[Provider, str] = {
    Provider.anthropic: "claude-sonnet-4-6",
    Provider.openai:    "gpt-4-turbo",
    Provider.bedrock:   "anthropic.claude-sonnet-4",
    Provider.azure:     "gpt-4-turbo",
}
_CHEAP_MODELS: dict[Provider, str] = {
    Provider.anthropic: "claude-haiku-4-5",
    Provider.openai:    "gpt-4o-mini",
    Provider.bedrock:   "anthropic.claude-haiku-4",
    Provider.azure:     "gpt-4o-mini",
}

TASK_TIER_MAP: dict[TaskType, TaskTier] = {
    TaskType.codebase_modeling:  TaskTier.STANDARD,
    TaskType.campaign_planning:  TaskTier.STANDARD,
    TaskType.code_analyzer:      TaskTier.STANDARD,
    TaskType.semantic_modeler:   TaskTier.LIGHT,
    TaskType.findings_judge:     TaskTier.STANDARD,
    TaskType.execution_judge:    TaskTier.HEAVY,
    TaskType.exploit_engine:     TaskTier.HEAVY,
    TaskType.exploit_script:     TaskTier.HEAVY,
    TaskType.poc_engine:         TaskTier.HEAVY,
    TaskType.evasion_strategist: TaskTier.HEAVY,
    TaskType.logic_modeler:      TaskTier.LIGHT,
    TaskType.agent_brain:        TaskTier.STANDARD,
    TaskType.challenger:         TaskTier.STANDARD,
    TaskType.severity_assessor:  TaskTier.LIGHT,
    TaskType.privesc_analysis:      TaskTier.HEAVY,
    TaskType.service_audit:         TaskTier.STANDARD,
    TaskType.package_vuln_analysis: TaskTier.STANDARD,
    TaskType.config_audit:          TaskTier.STANDARD,
    TaskType.network_exposure:      TaskTier.STANDARD,
    TaskType.chain_discovery:       TaskTier.HEAVY,
}

TIER_MODEL_MAP: dict[Provider, dict[TaskTier, str]] = {
    Provider.anthropic: {
        TaskTier.LIGHT:    "claude-haiku-4-5-20251001",
        TaskTier.STANDARD: "claude-sonnet-4-6",
        TaskTier.HEAVY:    "claude-opus-4-7",
    },
    Provider.openai: {
        TaskTier.LIGHT:    "gpt-4o-mini",
        TaskTier.STANDARD: "gpt-4o",
        TaskTier.HEAVY:    "o1",
    },
    Provider.bedrock: {
        TaskTier.LIGHT:    "anthropic.claude-haiku-4",
        TaskTier.STANDARD: "anthropic.claude-sonnet-4",
        TaskTier.HEAVY:    "anthropic.claude-opus-4",
    },
    Provider.azure: {
        TaskTier.LIGHT:    "gpt-4o-mini",
        TaskTier.STANDARD: "gpt-4-turbo",
        TaskTier.HEAVY:    "gpt-4o",
    },
}


# ── Cost pricing table (USD per 1M tokens: input, output) ────────────────────

_PRICING: dict[tuple[Provider, str], tuple[float, float]] = {
    (Provider.anthropic, "claude-sonnet-4-6"): (3.0, 15.0),
    (Provider.anthropic, "claude-haiku-4-5"):  (0.25, 1.25),
    (Provider.openai,    "gpt-4-turbo"):       (10.0, 30.0),
    (Provider.openai,    "gpt-4o-mini"):       (0.15, 0.6),
}


def _price(provider: Provider, model: str, usage: dict) -> float:
    pair = _PRICING.get((provider, model))
    if not pair:
        return 0.0
    inp, out = pair
    return (usage.get("input_tokens", 0) * inp + usage.get("output_tokens", 0) * out) / 1_000_000


# ── Fernet encryption ─────────────────────────────────────────────────────────

_fernet: Fernet | None = None
if settings.forge_secrets_key:
    _key = settings.forge_secrets_key
    _fernet = Fernet(_key.encode("ascii") if isinstance(_key, str) else _key)
elif not any([settings.anthropic_api_key, settings.openai_api_key, settings.aws_access_key_id]):
    logger.warning(
        "FORGE_SECRETS_KEY is not set and no deployment-level API keys found. "
        "LLM calls will fail unless at least one provider key is configured."
    )


def _encrypt_key(plaintext: str) -> bytes:
    if not _fernet:
        raise RuntimeError("FORGE_SECRETS_KEY is not set; cannot encrypt credentials")
    return _fernet.encrypt(plaintext.encode())


def _decrypt_key(ciphertext: bytes) -> str:
    if not _fernet:
        raise RuntimeError("FORGE_SECRETS_KEY is not set; cannot decrypt credentials")
    return _fernet.decrypt(ciphertext).decode()


class BudgetExceededError(Exception):
    """Raised when org's monthly LLM budget hard cap is reached."""
    def __init__(self, org_id, limit: float, current: float, estimated: float):
        self.org_id = org_id
        self.limit = limit
        self.current = current
        self.estimated = estimated
        super().__init__(
            f"Monthly LLM budget exceeded: ${current:.4f} spent + ${estimated:.4f} estimated "
            f"exceeds ${limit:.4f} limit"
        )


class RateLimitQueuedError(Exception):
    """Raised when org's provider rate limit is consistently exceeded after retries."""
    def __init__(self, org_id, provider: str, retry_after_seconds: int):
        self.org_id = org_id
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limit for {provider} exceeded; retry after {retry_after_seconds}s"
        )


# ── Env-var fallback credentials ──────────────────────────────────────────────

_ENV_CREDS: dict[Provider, ProviderCreds] = {
    Provider.anthropic: ProviderCreds(
        provider=Provider.anthropic,
        api_key=settings.anthropic_api_key or None,
    ),
    Provider.openai: ProviderCreds(
        provider=Provider.openai,
        api_key=settings.openai_api_key or None,
    ),
    Provider.bedrock: ProviderCreds(
        provider=Provider.bedrock,
        api_key=settings.aws_access_key_id or None,
        region=settings.aws_region,
        use_iam_role=not bool(settings.aws_access_key_id),
        extra={"aws_secret_access_key": settings.aws_secret_access_key},
    ),
    Provider.azure: ProviderCreds(
        provider=Provider.azure,
        api_key=settings.azure_openai_api_key or None,
        endpoint=settings.azure_openai_endpoint or None,
    ),
}


# ── Provider builders ─────────────────────────────────────────────────────────

def _build_anthropic(spec: LLMSpec, creds: ProviderCreds):
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=spec.model,
        api_key=creds.api_key,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
    )


def _build_openai(spec: LLMSpec, creds: ProviderCreds):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=spec.model,
        api_key=creds.api_key,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
    )


def _build_bedrock(spec: LLMSpec, creds: ProviderCreds):
    import boto3
    from langchain_aws import ChatBedrock
    region = creds.region or "us-east-1"
    if creds.use_iam_role:
        client = boto3.client("bedrock-runtime", region_name=region)
    else:
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=creds.api_key,
            aws_secret_access_key=creds.extra.get("aws_secret_access_key"),
        )
    return ChatBedrock(
        model_id=spec.model,
        client=client,
        model_kwargs={"max_tokens": spec.max_tokens, "temperature": spec.temperature},
    )


def _build_azure(spec: LLMSpec, creds: ProviderCreds):
    from langchain_openai import AzureChatOpenAI
    return AzureChatOpenAI(
        azure_deployment=spec.model,
        azure_endpoint=creds.endpoint or "",
        api_key=creds.api_key,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
    )


_BUILDERS: dict[Provider, object] = {
    Provider.anthropic: _build_anthropic,
    Provider.openai:    _build_openai,
    Provider.bedrock:   _build_bedrock,
    Provider.azure:     _build_azure,
}


# ── Resolution helpers ────────────────────────────────────────────────────────

async def _resolve_spec(task: TaskType, org_id: uuid.UUID | None) -> LLMSpec:
    if org_id:
        from app.models.org_llm import OrgLLMTaskConfig, OrgLLMCredential
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgLLMTaskConfig).where(
                    OrgLLMTaskConfig.org_id == org_id,
                    OrgLLMTaskConfig.task_type == task.value,
                )
            )).scalar_one_or_none()
            if row:
                return LLMSpec(
                    provider=Provider(row.provider),
                    model=row.model,
                    max_tokens=row.max_tokens or DEFAULT_TASK_SPECS[task].max_tokens,
                    temperature=row.temperature or 0.0,
                )
            # No explicit override — resolve via tier routing using org's configured provider
            cred_row = (await db.execute(
                select(OrgLLMCredential)
                .where(OrgLLMCredential.org_id == org_id)
                .order_by(OrgLLMCredential.created_at)
                .limit(1)
            )).scalar_one_or_none()
            if cred_row:
                provider = Provider(cred_row.provider)
                tier = TASK_TIER_MAP[task]
                model = TIER_MODEL_MAP[provider][tier]
                return LLMSpec(
                    provider=provider,
                    model=model,
                    max_tokens=DEFAULT_TASK_SPECS[task].max_tokens,
                )
    return DEFAULT_TASK_SPECS[task]


async def _resolve_credentials(provider: Provider, org_id: uuid.UUID | None) -> ProviderCreds:
    if org_id:
        from app.models.org_llm import OrgLLMCredential
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgLLMCredential).where(
                    OrgLLMCredential.org_id == org_id,
                    OrgLLMCredential.provider == provider.value,
                )
            )).scalar_one_or_none()
            if row:
                api_key = None
                if row.encrypted_key and _fernet:
                    api_key = _fernet.decrypt(row.encrypted_key).decode()
                return ProviderCreds(
                    provider=provider,
                    api_key=api_key,
                    region=row.region,
                    endpoint=row.endpoint,
                    use_iam_role=row.extra.get("use_iam_role", False) if row.extra else False,
                    extra=row.extra or {},
                )
    return _ENV_CREDS[provider]


# ── Retry wrapper ─────────────────────────────────────────────────────────────

class RetryLLM:
    def __init__(self, llm, retries: int = 3, backoff_base: float = 1.0):
        self.llm = llm
        self.retries = retries
        self.backoff_base = backoff_base

    async def ainvoke(self, messages, **kw):
        for attempt in range(self.retries + 1):
            try:
                return await self.llm.ainvoke(messages, **kw)
            except Exception as e:
                if not self._is_rate_limited(e) or attempt == self.retries:
                    raise
                wait = self.backoff_base * (2 ** attempt)
                logger.warning(
                    "LLM rate-limited, retrying in %ss (attempt %d/%d)",
                    wait, attempt + 1, self.retries,
                )
                await asyncio.sleep(wait)

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        return type(exc).__name__ in ("RateLimitError", "APIStatusError")


# ── Usage tracking ────────────────────────────────────────────────────────────

async def _log_usage(
    *,
    org_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    task: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_ms: int,
    compression_applied: bool = False,
    original_tokens: int | None = None,
    compression_savings_pct: float | None = None,
) -> None:
    if org_id is None:
        return
    from app.models.llm_usage import LLMUsageEvent
    try:
        async with AsyncSessionLocal() as db:
            event = LLMUsageEvent(
                org_id=org_id,
                engagement_id=engagement_id,
                task=task,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
                compression_applied=compression_applied,
                original_tokens=original_tokens,
                compression_savings_pct=compression_savings_pct,
            )
            db.add(event)
            await db.commit()
    except Exception:
        logger.exception("Failed to log LLM usage event")


async def _check_budget(
    org_id: uuid.UUID | None,
    provider: Provider,
    model: str,
    max_tokens: int,
    prompt_len: int,
) -> None:
    """Pre-call budget check. Raises BudgetExceededError if hard_cap would be exceeded."""
    if org_id is None:
        return
    pair = _PRICING.get((provider, model))
    if not pair:
        return
    inp_price, out_price = pair
    estimated_input = prompt_len / 4
    estimated_cost = (estimated_input * inp_price + max_tokens * out_price) / 1_000_000
    from app.models.org_llm import OrgBudget
    try:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgBudget).where(OrgBudget.org_id == org_id)
            )).scalar_one_or_none()
            if row is None:
                return
            if row.hard_cap and (row.current_spend_usd + estimated_cost) >= row.monthly_limit_usd:
                raise BudgetExceededError(
                    org_id=org_id,
                    limit=float(row.monthly_limit_usd),
                    current=float(row.current_spend_usd),
                    estimated=estimated_cost,
                )
    except BudgetExceededError:
        raise
    except Exception:
        logger.exception("Budget pre-check failed for org %s; allowing call", org_id)


async def _update_budget_spend(
    org_id: uuid.UUID | None,
    actual_cost: float,
) -> None:
    """Post-call: atomically add actual_cost to current_spend_usd, emit alert if threshold crossed."""
    if org_id is None or actual_cost == 0:
        return
    from app.models.org_llm import OrgBudget
    from sqlalchemy import text, update as sa_update
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                lock_id = int(uuid.UUID(str(org_id)).int % (2**62))
                await db.execute(text(f"SELECT pg_advisory_xact_lock({lock_id})"))
                await db.execute(
                    sa_update(OrgBudget)
                    .where(OrgBudget.org_id == org_id)
                    .values(current_spend_usd=OrgBudget.current_spend_usd + actual_cost)
                )
                row = (await db.execute(
                    select(OrgBudget).where(OrgBudget.org_id == org_id)
                )).scalar_one_or_none()
                if row and row.monthly_limit_usd > 0:
                    pct = (row.current_spend_usd / row.monthly_limit_usd) * 100
                    if pct >= row.alert_threshold_pct:
                        try:
                            from app.ws import progress as ws_progress
                            await ws_progress.broadcast(
                                "system",
                                "budget_alert",
                                {
                                    "org_id": str(org_id),
                                    "current_spend_usd": float(row.current_spend_usd),
                                    "monthly_limit_usd": float(row.monthly_limit_usd),
                                    "pct_used": round(pct, 1),
                                    "hard_cap": row.hard_cap,
                                },
                            )
                        except Exception:
                            logger.warning("budget_alert broadcast failed for org %s", org_id)
    except Exception:
        logger.exception("Budget spend update failed for org %s", org_id)


# ── Rate limiting (Redis sliding window) ──────────────────────────────────────

_DEFAULT_RATE_LIMITS: dict[str, dict[str, int]] = {
    "anthropic": {"tpm": 100_000, "rpm": 50},
    "openai":    {"tpm": 90_000,  "rpm": 60},
    "bedrock":   {"tpm": 80_000,  "rpm": 40},
    "azure":     {"tpm": 80_000,  "rpm": 40},
    # ollama: unlimited (0 = skip)
}

_RATE_LIMIT_LUA = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local now_ms = tonumber(ARGV[2])
local max_count = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now_ms - window_ms)
local count = redis.call('ZCARD', key)
if max_count > 0 and count >= max_count then
    return 0
end
redis.call('ZADD', key, now_ms, member)
redis.call('EXPIRE', key, 60)
return 1
"""

_redis_rl: object = None  # lazy singleton

async def _get_rl_redis():
    global _redis_rl
    if _redis_rl is None:
        from redis import asyncio as aioredis
        _redis_rl = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_rl


async def _check_rate_limit(
    org_id: uuid.UUID | None,
    provider: Provider,
    estimated_tokens: int,
) -> None:
    """Sliding-window rate limit check. Raises RateLimitQueuedError after 3 retries."""
    if org_id is None:
        return
    defaults = _DEFAULT_RATE_LIMITS.get(provider.value)
    if not defaults:
        return  # unknown provider or unlimited

    # Fetch any org-specific overrides
    tpm_limit = defaults["tpm"]
    rpm_limit = defaults["rpm"]
    try:
        from app.models.org_rate_limit import OrgRateLimitConfig
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgRateLimitConfig).where(
                    OrgRateLimitConfig.org_id == org_id,
                    OrgRateLimitConfig.provider == provider.value,
                )
            )).scalar_one_or_none()
            if row:
                if row.tpm_limit is not None:
                    tpm_limit = row.tpm_limit
                if row.rpm_limit is not None:
                    rpm_limit = row.rpm_limit
    except Exception:
        logger.exception("Rate limit config lookup failed; using defaults")

    import time as _time
    redis = await _get_rl_redis()
    org_str = str(org_id)
    prov_str = provider.value
    now_ms = int(_time.time() * 1000)
    window_ms = 60_000  # 1-minute sliding window

    for attempt in range(3):
        rpm_key = f"ratelimit:{org_str}:{prov_str}:rpm"
        tpm_key = f"ratelimit:{org_str}:{prov_str}:tpm"
        member = f"{now_ms}-{uuid.uuid4()}"

        rpm_ok = await redis.eval(_RATE_LIMIT_LUA, 1, rpm_key, window_ms, now_ms, rpm_limit, member)
        tpm_ok = await redis.eval(_RATE_LIMIT_LUA, 1, tpm_key, window_ms, now_ms, tpm_limit, f"tok-{member}")

        if rpm_ok and tpm_ok:
            return  # allowed

        wait = 2 ** attempt  # 1s, 2s, 4s
        logger.warning(
            "Rate limit hit for org %s provider %s (attempt %d/3); sleeping %ss",
            org_id, provider.value, attempt + 1, wait,
        )
        await asyncio.sleep(wait)
        now_ms = int(_time.time() * 1000)

    raise RateLimitQueuedError(
        org_id=org_id,
        provider=provider.value,
        retry_after_seconds=8,
    )


async def _record_rate_limit_usage(
    org_id: uuid.UUID | None,
    provider: Provider,
    actual_input_tokens: int,
    actual_output_tokens: int,
) -> None:
    """Update TPM window with actual token count after call completes."""
    if org_id is None:
        return
    try:
        import time as _time
        redis = await _get_rl_redis()
        org_str = str(org_id)
        prov_str = provider.value
        now_ms = int(_time.time() * 1000)
        tpm_key = f"ratelimit:{org_str}:{prov_str}:tpm"
        total_tokens = actual_input_tokens + actual_output_tokens
        member = f"actual-{now_ms}-{uuid.uuid4()}"
        await redis.zadd(tpm_key, {member: now_ms})
        await redis.expire(tpm_key, 60)
    except Exception:
        logger.exception("Rate limit usage record failed for org %s", org_id)


class TrackedLLM:
    def __init__(self, llm, *, task: TaskType, org_id, engagement_id, provider: Provider, model: str):
        self.llm = llm
        self.task = task
        self.org_id = org_id
        self.engagement_id = engagement_id
        self.provider = provider
        self.model = model

    async def ainvoke(self, messages, **kw):
        prompt_len = sum(
            len(str(getattr(m, "content", m))) for m in (messages if isinstance(messages, list) else [messages])
        )
        # Context compression
        from app.brain import context_manager as _ctx_mgr
        messages, _ctx_stats = await _ctx_mgr.prepare(
            messages, model=self.model, provider=self.provider.value
        )
        await _check_budget(
            org_id=self.org_id,
            provider=self.provider,
            model=self.model,
            max_tokens=getattr(self.llm, "max_tokens", 4000) if hasattr(self.llm, "max_tokens") else 4000,
            prompt_len=prompt_len,
        )
        await _check_rate_limit(
            org_id=self.org_id,
            provider=self.provider,
            estimated_tokens=prompt_len // 4,
        )
        t0 = time.monotonic()
        response = await self.llm.ainvoke(messages, **kw)
        usage = getattr(response, "usage_metadata", {}) or {}
        cost = _price(self.provider, self.model, usage)
        await _log_usage(
            org_id=self.org_id,
            engagement_id=self.engagement_id,
            task=self.task.value,
            provider=self.provider.value,
            model=self.model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=cost,
            duration_ms=int((time.monotonic() - t0) * 1000),
            compression_applied=_ctx_stats.compression_applied,
            original_tokens=_ctx_stats.original_tokens,
            compression_savings_pct=_ctx_stats.compression_savings_pct,
        )
        await _update_budget_spend(self.org_id, cost)
        await _record_rate_limit_usage(
            self.org_id, self.provider,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )
        return response


# ── Public API ────────────────────────────────────────────────────────────────

async def get_llm(
    task: TaskType,
    org_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
) -> TrackedLLM:
    """Resolve provider/model for task+org, build LangChain client, wrap for retry+tracking."""
    spec = await _resolve_spec(task, org_id)
    creds = await _resolve_credentials(spec.provider, org_id)
    raw = _BUILDERS[spec.provider](spec, creds)
    retrying = RetryLLM(raw, retries=3, backoff_base=1.0)
    return TrackedLLM(
        retrying,
        task=task,
        org_id=org_id,
        engagement_id=engagement_id,
        provider=spec.provider,
        model=spec.model,
    )
