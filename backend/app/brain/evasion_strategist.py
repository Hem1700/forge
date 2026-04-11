# backend/app/brain/evasion_strategist.py
import json
import re
import httpx
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a red team expert analyzing a target's defensive posture.
Given HTTP response headers, observed status codes, and target URL,
determine what defenses are in place and produce evasion guidelines.

Return ONLY valid JSON with:
- waf_detected: bool
- waf_type: string (cloudflare, akamai, aws_waf, modsecurity, unknown, none)
- rate_limit_detected: bool
- rate_limit_rps: int | null (estimated requests per second before throttle)
- guidelines: list of strings (specific evasion techniques to apply)
- stealth_level: string (aggressive, balanced, quiet)
"""


class _LLMWrapper:
    """Thin wrapper so ainvoke is a plain instance attribute (patchable)."""

    def __init__(self, llm):
        self._llm = llm

    async def ainvoke(self, messages):
        return await self._llm.ainvoke(messages)


class EvasionStrategist:
    def __init__(self):
        _chat = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=1000,
        )
        self._llm = _LLMWrapper(_chat)

    async def probe_defenses(self, target_url: str) -> tuple[dict, list[int]]:
        """Send passive probes to fingerprint the defensive stack."""
        headers = {}
        status_codes = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(target_url)
                headers = dict(resp.headers)
                status_codes.append(resp.status_code)
                r2 = await client.get(f"{target_url}/forge-probe-404")
                status_codes.append(r2.status_code)
        except Exception:
            pass
        return headers, status_codes

    async def analyze(self, target_url: str, headers: dict, response_codes: list[int]) -> dict:
        user_content = f"""
Target: {target_url}
Response Headers: {json.dumps(headers)}
Observed Status Codes: {response_codes}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
