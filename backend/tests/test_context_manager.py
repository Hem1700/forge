"""Tests for context window management and compression."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.brain.context_manager import (
    prepare, ContextStats, _count_tokens, _cache_key,
    _WARN_THRESHOLD, _COMPRESS_THRESHOLD, _CONTEXT_WINDOWS,
)


def _make_messages(n: int, chars_each: int = 100) -> list[dict]:
    return [{"role": "human" if i % 2 == 0 else "assistant", "content": "x" * chars_each}
            for i in range(n)]


@pytest.mark.asyncio
async def test_short_messages_pass_through():
    messages = _make_messages(3, chars_each=10)
    result, stats = await prepare(messages, model="claude-sonnet-4-6", provider="anthropic")
    assert result is messages
    assert stats.compression_applied is False
    assert stats.compression_savings_pct == 0.0


@pytest.mark.asyncio
async def test_context_stats_dataclass_defaults():
    stats = ContextStats()
    assert stats.compression_applied is False
    assert stats.original_tokens == 0
    assert stats.compression_savings_pct == 0.0


@pytest.mark.asyncio
async def test_four_or_fewer_messages_no_compression():
    messages = _make_messages(4, chars_each=50)
    result, stats = await prepare(messages, model="gpt-4o", provider="openai")
    assert stats.compression_applied is False


@pytest.mark.asyncio
async def test_compression_applied_for_large_context():
    # Create messages that fill >70% of a small context window
    # Patch context window to 1000 tokens so small input triggers compression
    big_messages = _make_messages(10, chars_each=500)  # ~1500 chars → ~500 tok estimate

    mock_summary = AsyncMock(return_value="[summary of middle]")
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)

    with patch("app.brain.context_manager._CONTEXT_WINDOWS", {"claude-sonnet-4-6": 100}), \
         patch("app.brain.context_manager._get_redis", AsyncMock(return_value=mock_redis)), \
         patch("app.brain.context_manager._summarize_middle", mock_summary):
        result, stats = await prepare(big_messages, model="claude-sonnet-4-6", provider="anthropic")

    assert stats.compression_applied is True
    assert stats.original_tokens > stats.final_tokens
    assert stats.compression_savings_pct > 0


@pytest.mark.asyncio
async def test_redis_cache_hit_avoids_second_summarize():
    big_messages = _make_messages(10, chars_each=500)
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="Cached summary text")
    mock_redis.setex = AsyncMock()
    mock_summarize = AsyncMock(return_value="Should not be called")

    with patch("app.brain.context_manager._CONTEXT_WINDOWS", {"claude-sonnet-4-6": 100}), \
         patch("app.brain.context_manager._get_redis", AsyncMock(return_value=mock_redis)), \
         patch("app.brain.context_manager._summarize_middle", mock_summarize):
        result, stats = await prepare(big_messages, model="claude-sonnet-4-6", provider="anthropic")

    # Cache hit means summarize was NOT called
    mock_summarize.assert_not_called()
    assert stats.compression_applied is True


@pytest.mark.asyncio
async def test_empty_messages_returns_unchanged():
    result, stats = await prepare([], model="gpt-4o-mini", provider="openai")
    assert result == []
    assert stats.compression_applied is False


def test_count_tokens_anthropic():
    msgs = [{"role": "human", "content": "hello world"}]
    count = _count_tokens(msgs, "anthropic")
    assert count > 0


def test_count_tokens_openai():
    msgs = [{"role": "human", "content": "hello world"}]
    count = _count_tokens(msgs, "openai")
    assert count > 0


def test_cache_key_is_deterministic():
    msgs = [{"role": "human", "content": "test message"}]
    k1 = _cache_key(msgs)
    k2 = _cache_key(msgs)
    assert k1 == k2
    assert k1.startswith("ctx_compress:")


def test_context_windows_covers_main_models():
    for model in ["claude-sonnet-4-6", "claude-haiku-4-5", "gpt-4o", "gpt-4o-mini"]:
        assert model in _CONTEXT_WINDOWS
