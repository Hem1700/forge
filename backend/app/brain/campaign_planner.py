# backend/app/brain/campaign_planner.py
import json
import re
from langchain_core.messages import HumanMessage, SystemMessage
from app.brain.llm_factory import get_llm, TaskType


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


class CampaignPlanner:
    def __init__(self, org_id=None):
        self._org_id = org_id

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
        llm = await get_llm(TaskType.campaign_planning, org_id=self._org_id)
        response = await llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
