# backend/tests/test_llm_factory.py
"""Unit tests for the LLM factory — resolution, builders, retry, tracking."""
from __future__ import annotations
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.brain.llm_factory import (
    TaskType, Provider, LLMSpec, ProviderCreds,
    DEFAULT_TASK_SPECS, get_llm, RetryLLM, TrackedLLM,
    _resolve_spec, _resolve_credentials,
)


# ── Resolution ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_spec_no_org_returns_default():
    spec = await _resolve_spec(TaskType.codebase_modeling, org_id=None)
    assert spec.provider == Provider.anthropic
    assert spec.model == "claude-sonnet-4-6"
    assert spec.max_tokens == 8000


@pytest.mark.asyncio
async def test_resolve_spec_no_org_haiku_for_judge():
    spec = await _resolve_spec(TaskType.findings_judge, org_id=None)
    assert spec.model == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_default_task_specs_covers_all_14():
    for task in TaskType:
        assert task in DEFAULT_TASK_SPECS, f"{task} missing from DEFAULT_TASK_SPECS"


@pytest.mark.asyncio
async def test_resolve_spec_org_override(monkeypatch):
    org_id = uuid.uuid4()

    fake_row = MagicMock()
    fake_row.provider = "openai"
    fake_row.model = "gpt-4-turbo"
    fake_row.max_tokens = 3000
    fake_row.temperature = 0.0

    async def fake_db_execute(*a, **kw):
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_row
        return result

    fake_session = AsyncMock()
    fake_session.execute = fake_db_execute

    class FakeCtx:
        async def __aenter__(self): return fake_session
        async def __aexit__(self, *a): pass

    monkeypatch.setattr("app.brain.llm_factory.AsyncSessionLocal", lambda: FakeCtx())

    spec = await _resolve_spec(TaskType.codebase_modeling, org_id=org_id)
    assert spec.provider == Provider.openai
    assert spec.model == "gpt-4-turbo"


@pytest.mark.asyncio
async def test_resolve_spec_org_no_override_returns_default(monkeypatch):
    """When org has no row in DB, fall back to DEFAULT_TASK_SPECS."""
    org_id = uuid.uuid4()

    async def fake_db_execute(*a, **kw):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    fake_session = AsyncMock()
    fake_session.execute = fake_db_execute

    class FakeCtx:
        async def __aenter__(self): return fake_session
        async def __aexit__(self, *a): pass

    monkeypatch.setattr("app.brain.llm_factory.AsyncSessionLocal", lambda: FakeCtx())

    spec = await _resolve_spec(TaskType.codebase_modeling, org_id=org_id)
    assert spec.model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_resolve_credentials_no_org_falls_back_to_env(monkeypatch):
    monkeypatch.setattr("app.brain.llm_factory._ENV_CREDS", {
        Provider.anthropic: ProviderCreds(provider=Provider.anthropic, api_key="test-key"),
    })
    creds = await _resolve_credentials(Provider.anthropic, org_id=None)
    assert creds.api_key == "test-key"


@pytest.mark.asyncio
async def test_resolve_credentials_org_decrypts_key(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    f = Fernet(key)
    encrypted = f.encrypt(b"my-secret-api-key")

    org_id = uuid.uuid4()
    fake_row = MagicMock()
    fake_row.encrypted_key = encrypted
    fake_row.region = None
    fake_row.endpoint = None
    fake_row.extra = {}

    async def fake_db_execute(*a, **kw):
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_row
        return result

    fake_session = AsyncMock()
    fake_session.execute = fake_db_execute

    class FakeCtx:
        async def __aenter__(self): return fake_session
        async def __aexit__(self, *a): pass

    monkeypatch.setattr("app.brain.llm_factory.AsyncSessionLocal", lambda: FakeCtx())
    monkeypatch.setattr("app.brain.llm_factory._fernet", f)

    creds = await _resolve_credentials(Provider.anthropic, org_id=org_id)
    assert creds.api_key == "my-secret-api-key"


# ── Retry ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_llm_succeeds_on_first_try():
    inner = AsyncMock()
    inner.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))
    retry = RetryLLM(inner, retries=3, backoff_base=0.001)
    result = await retry.ainvoke([])
    assert result.content == "ok"
    assert inner.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_retry_llm_retries_on_rate_limit():
    class FakeRateLimitError(Exception):
        pass
    FakeRateLimitError.__name__ = "RateLimitError"

    inner = AsyncMock()
    inner.ainvoke = AsyncMock(
        side_effect=[FakeRateLimitError("429"), FakeRateLimitError("429"), MagicMock(content="ok")]
    )
    retry = RetryLLM(inner, retries=3, backoff_base=0.001)
    result = await retry.ainvoke([])
    assert result.content == "ok"
    assert inner.ainvoke.call_count == 3


@pytest.mark.asyncio
async def test_retry_llm_raises_after_max_retries():
    class FakeRateLimitError(Exception):
        pass
    FakeRateLimitError.__name__ = "RateLimitError"

    inner = AsyncMock()
    inner.ainvoke = AsyncMock(side_effect=FakeRateLimitError("429"))
    retry = RetryLLM(inner, retries=2, backoff_base=0.001)
    with pytest.raises(FakeRateLimitError):
        await retry.ainvoke([])
    assert inner.ainvoke.call_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_retry_llm_does_not_retry_non_rate_limit():
    """Non-rate-limit exceptions should propagate immediately without retry."""
    inner = AsyncMock()
    inner.ainvoke = AsyncMock(side_effect=ValueError("bad input"))
    retry = RetryLLM(inner, retries=3, backoff_base=0.001)
    with pytest.raises(ValueError):
        await retry.ainvoke([])
    assert inner.ainvoke.call_count == 1


# ── Tracking ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tracked_llm_logs_usage(monkeypatch):
    logged = []

    async def fake_log_usage(**kwargs):
        logged.append(kwargs)

    monkeypatch.setattr("app.brain.llm_factory._log_usage", fake_log_usage)

    inner = AsyncMock()
    response = MagicMock()
    response.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    inner.ainvoke = AsyncMock(return_value=response)

    org_id = uuid.uuid4()
    tracked = TrackedLLM(
        inner,
        task=TaskType.codebase_modeling,
        org_id=org_id,
        engagement_id=None,
        provider=Provider.anthropic,
        model="claude-sonnet-4-6",
    )
    await tracked.ainvoke([])

    assert len(logged) == 1
    assert logged[0]["input_tokens"] == 10
    assert logged[0]["output_tokens"] == 5
    assert logged[0]["org_id"] == org_id


@pytest.mark.asyncio
async def test_tracked_llm_handles_missing_usage_metadata(monkeypatch):
    logged = []

    async def fake_log_usage(**kwargs):
        logged.append(kwargs)

    monkeypatch.setattr("app.brain.llm_factory._log_usage", fake_log_usage)

    inner = AsyncMock()
    response = MagicMock(spec=["content"])  # no usage_metadata attribute
    inner.ainvoke = AsyncMock(return_value=response)

    tracked = TrackedLLM(
        inner,
        task=TaskType.findings_judge,
        org_id=uuid.uuid4(),
        engagement_id=None,
        provider=Provider.anthropic,
        model="claude-haiku-4-5",
    )
    await tracked.ainvoke([])
    assert logged[0]["input_tokens"] == 0
    assert logged[0]["output_tokens"] == 0


# ── get_llm integration ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_llm_returns_tracked_llm(monkeypatch):
    fake_raw = AsyncMock()
    fake_raw.ainvoke = AsyncMock(return_value=MagicMock(
        content="hi", usage_metadata={"input_tokens": 1, "output_tokens": 1}
    ))

    monkeypatch.setattr("app.brain.llm_factory._BUILDERS", {
        Provider.anthropic: lambda spec, creds: fake_raw,
    })
    monkeypatch.setattr("app.brain.llm_factory._log_usage", AsyncMock())

    llm = await get_llm(TaskType.codebase_modeling, org_id=None)
    assert isinstance(llm, TrackedLLM)
