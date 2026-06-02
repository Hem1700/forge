# backend/tests/test_usage_stats.py
"""Unit tests for LLM usage/latency aggregation (pure functions, no DB)."""
from app.brain.usage_stats import _percentile, aggregate_latency_stats


def test_percentile_empty():
    assert _percentile([], 50) == 0.0


def test_percentile_nearest_rank():
    # ceil(0.5*4)=2 -> index 1 -> 20 ; ceil(0.95*4)=4 -> index 3 -> 40
    assert _percentile([10, 20, 30, 40], 50) == 20.0
    assert _percentile([10, 20, 30, 40], 95) == 40.0


def test_percentile_single_value():
    assert _percentile([5], 50) == 5.0
    assert _percentile([5], 95) == 5.0


def test_percentile_hundred():
    vals = list(range(1, 101))  # 1..100
    assert _percentile(vals, 50) == 50.0   # ceil(50)=50 -> index 49 -> 50
    assert _percentile(vals, 95) == 95.0   # ceil(95)=95 -> index 94 -> 95


def test_aggregate_empty():
    assert aggregate_latency_stats([]) == []


def test_aggregate_groups_by_task_sorted():
    rows = [
        {"task": "code_analyzer", "duration_ms": 50, "input_tokens": 100, "output_tokens": 10},
        {"task": "campaign_planning", "duration_ms": 100, "input_tokens": 200, "output_tokens": 20},
        {"task": "campaign_planning", "duration_ms": 200, "input_tokens": 400, "output_tokens": 40},
        {"task": "campaign_planning", "duration_ms": 300, "input_tokens": 600, "output_tokens": 60},
    ]
    out = aggregate_latency_stats(rows)
    # sorted by task name -> campaign_planning first
    assert [r["task"] for r in out] == ["campaign_planning", "code_analyzer"]

    cp = out[0]
    assert cp["calls"] == 3
    assert cp["latency_ms"]["min"] == 100
    assert cp["latency_ms"]["max"] == 300
    assert cp["latency_ms"]["avg"] == 200.0
    # sorted durations [100,200,300]: p50 ceil(1.5)=2 ->idx1 ->200 ; p95 ceil(2.85)=3 ->idx2 ->300
    assert cp["latency_ms"]["p50"] == 200.0
    assert cp["latency_ms"]["p95"] == 300.0
    # token distribution present
    assert cp["input_tokens"]["avg"] == 400.0
    assert cp["output_tokens"]["avg"] == 40.0

    ca = out[1]
    assert ca["calls"] == 1
    assert ca["latency_ms"]["avg"] == 50.0
    assert ca["latency_ms"]["p95"] == 50.0
