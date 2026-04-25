"""LLM judge for raw findings — flags likely false positives and groups duplicates.

Runs concurrently with the swarm: after each agent commits a batch of findings,
the orchestrator spawns a judge task to grade them. The verdict is persisted to
finding.triage_judgment and broadcast as a `finding_judged` event so the UI can
update without waiting for the campaign to finish.
"""
from __future__ import annotations

import json
import re
from typing import Iterable

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.brain.codebase_modeler import _LLMWrapper
from app.config import settings


SYSTEM_PROMPT = """You are a senior application-security engineer triaging findings produced by automated scanners.

For each finding, decide:
- likely_false_positive: true ONLY if you have strong reason to believe the finding is noise — a test fixture, an obvious placeholder, a comment-only match, a benign default, or a pattern hit that does not represent an exploitable issue. When uncertain, return false.
- confidence: 0.0–1.0 — how confident you are about likely_false_positive. Use 0.5 if you genuinely cannot tell.
- reasoning: ONE sentence (max 25 words) explaining the decision. Cite specific evidence/file/line where relevant.
- dedup_signature: a short stable string that groups near-duplicate findings (e.g. "sqli:users_table:id_param", "jwt:alg_none:/api/admin", "secret:aws_key:terraform.tfvars"). Use the same signature for findings that are obviously the same underlying issue. Empty string for singletons.
- suggested_severity: optional — only set if you strongly disagree with the input severity. One of: critical, high, medium, low, info.

Return ONLY a valid JSON array, same length and same order as the input. Each item:
{
  "id": "<finding id from input>",
  "likely_false_positive": bool,
  "confidence": float,
  "reasoning": str,
  "dedup_signature": str,
  "suggested_severity": str|null
}
"""

MAX_BATCH = 12      # tokens per call — keep batches modest
MAX_CHARS = 600     # truncate description/evidence per finding


class FindingsJudge:
    def __init__(self) -> None:
        self._llm = _LLMWrapper(ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2500,
        ))

    async def judge(self, findings: Iterable[dict]) -> list[dict]:
        """Judge a batch of findings. Returns parallel list of verdicts."""
        compact = [
            {
                "id": str(f.get("id")),
                "vulnerability_class": str(f.get("vulnerability_class") or f.get("vulnerability") or "")[:80],
                "severity": str(f.get("severity") or "medium"),
                "file": str(f.get("affected_surface") or f.get("file") or "")[:200],
                "line_hint": str(f.get("line_hint") or ""),
                "description": str(f.get("description") or "")[:MAX_CHARS],
                "evidence": _flatten(f.get("evidence"))[:MAX_CHARS],
            }
            for f in findings
        ]
        if not compact:
            return []

        results: list[dict] = []
        for i in range(0, len(compact), MAX_BATCH):
            batch = compact[i:i + MAX_BATCH]
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(batch, indent=2)),
            ]
            try:
                response = await self._llm.ainvoke(messages)
                text = response.content.strip()
                text = re.sub(r'^```json\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    results.extend(parsed)
                else:
                    results.extend(_blanks(batch))
            except Exception:
                results.extend(_blanks(batch))

        # Keyed by id for safe matching even if the LLM reorders
        by_id = {str(r.get("id")): r for r in results if isinstance(r, dict)}
        return [by_id.get(c["id"], _blank(c["id"])) for c in compact]


def _flatten(evidence) -> str:
    if isinstance(evidence, list):
        return "\n".join(str(e) for e in evidence)
    return str(evidence or "")


def _blank(finding_id: str) -> dict:
    return {
        "id": finding_id,
        "likely_false_positive": False,
        "confidence": 0.0,
        "reasoning": "judge unavailable — no verdict",
        "dedup_signature": "",
        "suggested_severity": None,
    }


def _blanks(batch: list[dict]) -> list[dict]:
    return [_blank(c["id"]) for c in batch]
