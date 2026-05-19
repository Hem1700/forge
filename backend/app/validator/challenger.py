# backend/app/validator/challenger.py
import json
import re
from langchain_core.messages import HumanMessage, SystemMessage
from app.brain.llm_factory import get_llm, TaskType


SYSTEM_PROMPT = """You are a skeptical security researcher verifying whether a reported finding is real.
Given a finding report, evaluate: is this reproducible? Is the evidence convincing?

Return ONLY valid JSON:
- reproduced: bool (would you be able to reproduce this with the given steps?)
- confidence: float (0.0–1.0 — how confident are you this is a real vulnerability?)
- notes: string (your assessment)
"""


class Challenger:
    def __init__(self, org_id=None):
        self._org_id = org_id

    async def challenge(self, finding: dict) -> dict:
        user_content = f"""
Finding: {finding.get('title')}
Class: {finding.get('vulnerability_class')}
Surface: {finding.get('affected_surface')}
Description: {finding.get('description')}
Reproduction Steps: {json.dumps(finding.get('reproduction_steps', []))}
Evidence: {json.dumps(finding.get('evidence', []))}
"""
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]
        llm = await get_llm(TaskType.challenger, org_id=self._org_id)
        response = await llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
