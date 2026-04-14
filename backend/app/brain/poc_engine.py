# backend/app/brain/poc_engine.py
from __future__ import annotations
import json
import re
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import settings

SYSTEM_PROMPT = """You are a senior penetration tester generating a detailed, runnable proof-of-concept exploit script for a confirmed security vulnerability. This is for authorized security testing only.

Given a vulnerability finding and target context, return ONLY valid JSON with these exact fields:
- language: string — exactly one of: "python", "bash"
  Language selection rules:
  - sqli, xss, ssrf, auth_bypass, idor, open_redirect → "python"
  - cmdi, path_traversal (simple HTTP) → "bash"
  - buffer_overflow, format_string, use_after_free, rop → "python"
  - default → "python"
- filename: string — descriptive filename like "poc_sqli_api_users.py" or "poc_cmdi_run.sh"
- script: string — the complete, runnable exploit script. Must:
  - Use the ACTUAL target URL/path from the context (not a placeholder)
  - Use real parameter names and paths from the evidence
  - Include realistic, working payloads for the vulnerability class
  - Be complete and self-contained (no missing imports)
  - For Python: include a main() or if __name__ == '__main__' block
  - For bash: include a shebang line
- setup: array of strings — shell commands to install dependencies (e.g. ["pip install requests"]). Empty array [] if none needed.
- notes: string — one sentence of important usage notes (e.g. what to replace, expected output). Empty string "" if no notes needed.
- sequence_diagram: string — valid Mermaid sequenceDiagram showing the request/response flow of the exploit. Example format:
  "sequenceDiagram\\n  participant Attacker\\n  participant Server\\n  Attacker->>Server: GET /api/users?id=1' OR '1'='1\\n  Server-->>Attacker: 200 OK — all rows returned"
  Use ->> for requests and -->> for responses. Keep participant names as single words.

The script must be specific to the target — use the actual URL, endpoints, and parameters from the finding evidence. Not a generic template.
"""


class _LLMWrapper:
    """Thin wrapper so ainvoke is a plain instance attribute — patchable in tests."""
    def __init__(self, llm):
        self._llm = llm

    async def ainvoke(self, messages):
        return await self._llm.ainvoke(messages)


class PoCEngine:
    def __init__(self):
        _chat = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=8000,
        )
        self._llm = _LLMWrapper(_chat)

    async def generate(self, finding: dict, context: dict) -> dict:
        evidence = finding.get("evidence", [])
        evidence_str = json.dumps(evidence)[:1000] if evidence else "none"

        user_content = (
            f"Target Context:\n"
            f"- URL/Path: {context.get('target_url') or context.get('target_path', 'unknown')}\n"
            f"- Type: {context.get('target_type', 'web')}\n"
            f"- App Type: {context.get('app_type', 'unknown')}\n\n"
            f"Vulnerability Finding:\n"
            f"- Class: {finding.get('vulnerability_class', 'unknown')}\n"
            f"- Severity: {finding.get('severity', 'medium')}\n"
            f"- Location: {finding.get('affected_surface', 'unknown')}\n"
            f"- Description: {finding.get('description', '')}\n"
            f"- Evidence: {evidence_str}\n"
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
            raise ValueError(f"PoCEngine: LLM returned unparseable JSON: {exc}\nRaw: {text[:300]}") from exc
