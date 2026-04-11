# backend/app/brain/campaign_planner.py
import json
import re
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a senior penetration tester generating a prioritized attack campaign.
Given a semantic model of the target application and historical knowledge base results,
generate a ranked list of attack hypotheses.

Return ONLY a valid JSON array. Each item must have:
- title: string (short hypothesis name)
- surface: string (specific endpoint or component to test)
- attack_class: string (sqli, xss, idor, auth_bypass, race_condition, business_logic, ssrf, xxe, etc.)
- reasoning: string (why this hypothesis is viable for THIS app)
- confidence: float (0.0–1.0, based on app type + KB history)
- priority: string (critical, high, medium, low)

Order by priority descending, then confidence descending. Maximum 15 hypotheses.
"""


class _LLMWrapper:
    """Thin wrapper so ainvoke is a plain instance attribute (patchable)."""

    def __init__(self, llm):
        self._llm = llm

    async def ainvoke(self, messages):
        return await self._llm.ainvoke(messages)


class CampaignPlanner:
    def __init__(self):
        _chat = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=3000,
        )
        self._llm = _LLMWrapper(_chat)

    async def generate(self, semantic_model: dict, kb_context: list[dict]) -> list[dict]:
        kb_summary = "\n".join(
            f"- {r.get('attack_class', '')} ({r.get('technique', '')}): {r.get('outcome', '')} hit rate {r.get('score', 0):.2f}"
            for r in kb_context[:10]
        ) or "No prior history for this target profile."

        user_content = f"""
Semantic App Model:
{json.dumps(semantic_model, indent=2)}

Relevant Knowledge Base History:
{kb_summary}
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
