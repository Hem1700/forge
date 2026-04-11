# backend/app/validator/severity.py
import json
import re
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a security expert assessing the severity of a vulnerability.
Given the finding and the application's semantic model, assess business impact.

Return ONLY valid JSON:
- severity: string (critical, high, medium, low, info)
- cvss_score: float (0.0–10.0)
- business_impact: string (one sentence)
- justification: string (why this severity)
"""


class _LLMWrapper:
    def __init__(self, llm):
        self._llm = llm

    async def ainvoke(self, messages):
        return await self._llm.ainvoke(messages)


class SeverityAssessor:
    def __init__(self):
        self._llm = _LLMWrapper(ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=500,
        ))

    async def assess(self, finding: dict, semantic_model: dict) -> dict:
        user_content = f"""
Finding: {finding.get('title')}
Class: {finding.get('vulnerability_class')}
Surface: {finding.get('affected_surface')}
Description: {finding.get('description')}
App Type: {semantic_model.get('app_type', 'unknown')}
User Roles: {semantic_model.get('user_roles', [])}
Business Flows: {semantic_model.get('business_flows', [])}
"""
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
