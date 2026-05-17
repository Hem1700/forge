"""Unit tests for forge_cli.ci pure functions."""
from forge_cli.ci import (
    threshold_breached,
    severity_counts,
    format_findings_markdown,
    build_callback_payload,
)

_FINDINGS = [
    {"severity": "critical", "vulnerability_class": "RCE", "affected_surface": "/cmd"},
    {"severity": "high", "vulnerability_class": "SQLi", "affected_surface": "/api/users"},
    {"severity": "medium", "vulnerability_class": "XSS", "affected_surface": "/search"},
]


# ── threshold_breached ────────────────────────────────────────────────────────

def test_threshold_breached_fail_on_none():
    assert threshold_breached(_FINDINGS, "none") is False


def test_threshold_breached_no_findings():
    assert threshold_breached([], "high") is False


def test_threshold_breached_below_threshold():
    assert threshold_breached([{"severity": "low"}], "high") is False


def test_threshold_breached_at_threshold():
    assert threshold_breached(_FINDINGS, "high") is True


def test_threshold_breached_critical_only():
    assert threshold_breached([{"severity": "critical"}], "critical") is True


def test_threshold_breached_medium_catches_high():
    assert threshold_breached([{"severity": "high"}], "medium") is True


def test_threshold_breached_unknown_severity():
    assert threshold_breached([{"severity": "unknown"}], "high") is False


def test_threshold_breached_no_severity_key():
    # finding with no severity key defaults to "info" — below high threshold
    assert threshold_breached([{"vulnerability_class": "XSS"}], "high") is False


# ── severity_counts ───────────────────────────────────────────────────────────

def test_severity_counts_empty():
    c = severity_counts([])
    assert c == {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}


def test_severity_counts_mixed():
    c = severity_counts(_FINDINGS)
    assert c["critical"] == 1
    assert c["high"] == 1
    assert c["medium"] == 1
    assert c["low"] == 0
    assert c["info"] == 0


# ── format_findings_markdown ──────────────────────────────────────────────────

def test_format_findings_markdown_contains_header():
    md = format_findings_markdown("abc-123", [], "http://localhost:8080")
    assert "## FORGE Security Scan" in md


def test_format_findings_markdown_contains_engagement_link():
    md = format_findings_markdown("abc-123", [], "http://localhost:8080")
    assert "abc-123" in md
    assert "http://localhost:8080" in md


def test_format_findings_markdown_includes_vuln_classes():
    md = format_findings_markdown("abc-123", _FINDINGS, "http://localhost:8080")
    assert "RCE" in md
    assert "SQLi" in md


def test_format_findings_markdown_no_findings_still_valid():
    md = format_findings_markdown("abc-123", [], "http://localhost:8080")
    assert "View full engagement" in md


def test_format_findings_markdown_severity_table_counts():
    md = format_findings_markdown("abc-123", _FINDINGS, "http://localhost:8080")
    assert "| Critical | 1 |" in md
    assert "| High | 1 |" in md
    assert "| Medium | 1 |" in md


# ── build_callback_payload ────────────────────────────────────────────────────

def test_build_callback_payload_fields():
    eng = {"id": "abc", "status": "complete", "target_url": "https://example.com"}
    payload = build_callback_payload(eng, _FINDINGS, True)
    assert payload["engagement_id"] == "abc"
    assert payload["status"] == "complete"
    assert payload["findings_count"] == 3
    assert payload["threshold_breached"] is True
    assert payload["severity_counts"]["critical"] == 1
    assert len(payload["findings"]) == 3


def test_build_callback_payload_not_breached():
    eng = {"id": "xyz", "status": "complete", "target_url": "https://example.com"}
    payload = build_callback_payload(eng, [], False)
    assert payload["threshold_breached"] is False
    assert payload["findings_count"] == 0
