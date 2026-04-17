# backend/app/brain/execution_judge.py
from __future__ import annotations
import json
import re
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import settings

SYSTEM_PROMPT = """You are a senior penetration tester reviewing the output of a live exploit execution. Assess whether the exploit succeeded.

Given the vulnerability details, the script that was run, and its captured output, return ONLY valid JSON with these exact fields:
- verdict: string — exactly one of: "confirmed", "failed", "inconclusive"
  - "confirmed": output clearly demonstrates successful exploitation (data extracted, command executed with output, auth bypassed, session obtained)
  - "failed": script ran but did not achieve exploitation (errors, access denied, empty output, target patched/unreachable)
  - "inconclusive": output exists but it's unclear whether exploitation succeeded (generic responses, partial output, ambiguous results)
- confidence: float — your confidence in this verdict, 0.0 to 1.0
- reasoning: string — 1-3 sentences explaining what in the output led to this verdict. Be specific about what you saw (or didn't see).
"""


class _LLMWrapper:
    """Thin wrapper so ainvoke is a plain instance attribute — patchable in tests."""
    def __init__(self, llm):
        self._llm = llm

    async def ainvoke(self, messages):
        return await self._llm.ainvoke(messages)


class ExecutionJudge:
    """Assesses whether a live exploit execution succeeded.

    Uses an LLM to evaluate script output against the expected exploitation
    outcome, returning a verdict (confirmed/failed/inconclusive) with
    confidence score and reasoning.
    """

    def __init__(self):
        _chat = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2000,
        )
        self._llm = _LLMWrapper(_chat)

    async def judge(
        self,
        finding: dict,
        script: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> dict:
        """Assess whether an exploit execution succeeded.

        Args:
            finding: Vulnerability details (vulnerability_class, severity, etc.)
            script: The exploit script that was executed.
            stdout: Captured standard output from the execution.
            stderr: Captured standard error from the execution.
            exit_code: Process exit code (0 typically means success).

        Returns:
            Dict with verdict, confidence, and reasoning fields.
        """
        user_content = (
            f"Vulnerability:\n"
            f"- Class: {finding.get('vulnerability_class', 'unknown')}\n"
            f"- Severity: {finding.get('severity', 'unknown')}\n"
            f"- Location: {finding.get('affected_surface', 'unknown')}\n"
            f"- Description: {finding.get('description', '')}\n\n"
            f"Script executed (first 500 chars):\n{script[:500]}\n\n"
            f"exit_code={exit_code}\n\n"
            f"stdout (first 2000 chars):\n{stdout[:2000] if stdout else '(empty)'}\n\n"
            f"stderr (first 500 chars):\n{stderr[:500] if stderr else '(empty)'}\n"
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"ExecutionJudge: LLM returned unparseable JSON: {exc}\nRaw: {text[:300]}"
            ) from exc
