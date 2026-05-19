# backend/app/validator/severity.py
import json
import re
from langchain_core.messages import HumanMessage, SystemMessage
from app.brain.llm_factory import get_llm, TaskType


SYSTEM_PROMPT = """You are a security expert assessing the severity of a vulnerability.
Given the finding and the application's semantic model, assess business impact.

Return ONLY valid JSON:
- severity: string (critical, high, medium, low, info)
- cvss_score: float (0.0–10.0)
- business_impact: string (one sentence)
- justification: string (why this severity)
"""


class SeverityAssessor:
    def __init__(self, org_id=None):
        self._org_id = org_id

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
        llm = await get_llm(TaskType.severity_assessor, org_id=self._org_id)
        response = await llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
