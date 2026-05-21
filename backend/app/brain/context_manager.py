# backend/app/brain/context_manager.py
"""Context window management: token counting, compression, and caching."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Context window sizes per model (tokens)
_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-haiku-4-5":         200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-sonnet-4-6":        200_000,
    "claude-opus-4-7":          200_000,
    "gpt-4o":                   128_000,
    "gpt-4o-mini":              128_000,
    "gpt-4-turbo":              128_000,
    "o1":                       128_000,
}
_DEFAULT_CONTEXT_WINDOW = 128_000

# Thresholds (fraction of context window)
_WARN_THRESHOLD = float(getattr(settings, "context_warn_pct", 0.70))
_COMPRESS_THRESHOLD = float(getattr(settings, "context_compress_pct", 0.85))

_redis_ctx = None


async def _get_redis():
    global _redis_ctx
    if _redis_ctx is None:
        from redis import asyncio as aioredis
        _redis_ctx = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_ctx


def _count_tokens_anthropic(messages: list[Any]) -> int:
    """Estimate tokens using character length / 3.5 (conservative)."""
    total = 0
    for m in messages:
        content = getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else str(m))
        total += len(str(content)) // 3
    return total


def _count_tokens_openai(messages: list[Any]) -> int:
    """Use tiktoken cl100k_base for OpenAI models."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for m in messages:
            content = getattr(m, "content", None) or (m.get("content", "") if isinstance(m, dict) else str(m))
            total += len(enc.encode(str(content)))
        return total
    except Exception:
        return sum(len(str(getattr(m, "content", m))) // 4 for m in messages)


def _count_tokens(messages: list[Any], provider: str) -> int:
    if provider in ("anthropic", "bedrock"):
        return _count_tokens_anthropic(messages)
    if provider in ("openai", "azure"):
        return _count_tokens_openai(messages)
    return sum(len(str(getattr(m, "content", m))) // 4 for m in messages)


def _msg_to_dict(m: Any) -> dict:
    if isinstance(m, dict):
        return m
    return {
        "role": getattr(m, "type", "human"),
        "content": str(getattr(m, "content", m)),
    }


def _cache_key(middle: list[Any]) -> str:
    payload = json.dumps([_msg_to_dict(m) for m in middle], sort_keys=True)
    return "ctx_compress:" + hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class ContextStats:
    original_tokens: int = 0
    final_tokens: int = 0
    compression_applied: bool = False
    compression_savings_pct: float = 0.0


async def _summarize_middle(middle: list[Any], provider: str) -> str:
    """Call a LIGHT-tier LLM directly (bypasses TrackedLLM to avoid recursion)."""
    from app.brain.llm_factory import (
        _build_anthropic, _build_openai, _build_azure, _build_bedrock,
        _ENV_CREDS, LLMSpec, Provider,
    )
    try:
        prov = Provider(provider) if provider in [p.value for p in Provider] else Provider.anthropic
        spec = LLMSpec(provider=prov, model={
            Provider.anthropic: "claude-haiku-4-5",
            Provider.openai: "gpt-4o-mini",
            Provider.bedrock: "anthropic.claude-haiku-4",
            Provider.azure: "gpt-4o-mini",
        }.get(prov, "claude-haiku-4-5"), max_tokens=1000)
        creds = _ENV_CREDS[prov]
        builders = {
            Provider.anthropic: _build_anthropic,
            Provider.openai: _build_openai,
            Provider.bedrock: _build_bedrock,
            Provider.azure: _build_azure,
        }
        llm = builders[prov](spec, creds)
        from langchain_core.messages import HumanMessage, SystemMessage
        middle_text = "\n".join(
            f"[{_msg_to_dict(m).get('role','?')}]: {_msg_to_dict(m).get('content','')[:500]}"
            for m in middle[:20]
        )
        prompt = [
            SystemMessage(content="Summarize the following conversation history concisely, preserving key facts and context needed for continuing the conversation:"),
            HumanMessage(content=middle_text),
        ]
        result = await llm.ainvoke(prompt)
        return getattr(result, "content", str(result))
    except Exception as e:
        logger.warning("Context compression summary failed: %s", e)
        return "[Previous conversation summarized]"


async def prepare(
    messages: list[Any],
    model: str,
    provider: str,
) -> tuple[list[Any], ContextStats]:
    """
    Check context length and compress if needed.
    Returns (possibly-compressed messages, ContextStats).
    """
    stats = ContextStats()
    if not messages:
        return messages, stats

    max_ctx = _CONTEXT_WINDOWS.get(model, _DEFAULT_CONTEXT_WINDOW)
    original_tokens = _count_tokens(messages, provider)
    stats.original_tokens = original_tokens
    stats.final_tokens = original_tokens

    fill_ratio = original_tokens / max_ctx

    if fill_ratio < _WARN_THRESHOLD:
        return messages, stats

    # Need some compression
    # Keep: first message (system/context) + last 3 messages
    if len(messages) <= 4:
        stats.final_tokens = original_tokens
        return messages, stats

    head = messages[:1]
    middle = messages[1:-3]
    tail = messages[-3:]

    # Try Redis cache first
    try:
        redis = await _get_redis()
        ck = _cache_key(middle)
        cached = await redis.get(ck)
    except Exception:
        redis = None
        ck = None
        cached = None

    if cached:
        summary_text = cached
    else:
        summary_text = await _summarize_middle(middle, provider)
        if redis and ck:
            try:
                await redis.setex(ck, 3600, summary_text)
            except Exception:
                pass

    # Build compressed summary message
    try:
        from langchain_core.messages import HumanMessage
        summary_msg = HumanMessage(content=f"[Context summary: {summary_text}]")
    except ImportError:
        summary_msg = {"role": "human", "content": f"[Context summary: {summary_text}]"}

    compressed = head + [summary_msg] + tail
    final_tokens = _count_tokens(compressed, provider)

    stats.final_tokens = final_tokens
    stats.compression_applied = True
    stats.compression_savings_pct = round((1 - final_tokens / original_tokens) * 100, 1)

    logger.info(
        "Context compressed: %d → %d tokens (%.1f%% savings, model=%s)",
        original_tokens, final_tokens, stats.compression_savings_pct, model,
    )
    return compressed, stats
