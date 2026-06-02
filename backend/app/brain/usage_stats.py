# backend/app/brain/usage_stats.py
"""Aggregation helpers for LLM usage/latency observability.

Computes per-task-type latency percentiles and token-usage distribution from
LLMUsageEvent rows. Percentiles are computed in Python (nearest-rank) so the
logic is portable across Postgres/MySQL and trivially unit-testable.
"""
from __future__ import annotations

import math
from collections import defaultdict


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted list. Returns 0.0 if empty.

    pct is in [0, 100]. Uses index = ceil(pct/100 * n) - 1, clamped to [0, n-1].
    """
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    k = math.ceil((pct / 100.0) * n) - 1
    k = max(0, min(k, n - 1))
    return float(sorted_vals[k])


def _dist(values: list[int]) -> dict:
    """Return avg/p50/p95/min/max for a list of numeric values."""
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "min": 0, "max": 0}
    s = sorted(values)
    return {
        "avg": round(sum(s) / len(s), 2),
        "p50": _percentile(s, 50),
        "p95": _percentile(s, 95),
        "min": s[0],
        "max": s[-1],
    }


def aggregate_latency_stats(rows: list[dict]) -> list[dict]:
    """Group rows by `task` and compute latency + token distributions per task.

    Each input row must have keys: task, duration_ms, input_tokens, output_tokens.
    Returns a list of per-task dicts sorted by task name.
    """
    by_task: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {"duration_ms": [], "input_tokens": [], "output_tokens": []}
    )
    for r in rows:
        task = r["task"]
        by_task[task]["duration_ms"].append(int(r.get("duration_ms", 0) or 0))
        by_task[task]["input_tokens"].append(int(r.get("input_tokens", 0) or 0))
        by_task[task]["output_tokens"].append(int(r.get("output_tokens", 0) or 0))

    out: list[dict] = []
    for task in sorted(by_task.keys()):
        d = by_task[task]
        lat = _dist(d["duration_ms"])
        inp = _dist(d["input_tokens"])
        outp = _dist(d["output_tokens"])
        out.append({
            "task": task,
            "calls": len(d["duration_ms"]),
            "latency_ms": lat,
            "input_tokens": {"avg": inp["avg"], "p50": inp["p50"], "p95": inp["p95"]},
            "output_tokens": {"avg": outp["avg"], "p50": outp["p50"], "p95": outp["p95"]},
        })
    return out
