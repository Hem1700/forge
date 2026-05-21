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
            )
            db.add(event)
            await db.commit()
    except Exception:
        logger.exception("Failed to log LLM usage event")


class TrackedLLM:
    def __init__(self, llm, *, task: TaskType, org_id, engagement_id, provider: Provider, model: str):
        self.llm = llm
        self.task = task
        self.org_id = org_id
        self.engagement_id = engagement_id
        self.provider = provider
        self.model = model

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
