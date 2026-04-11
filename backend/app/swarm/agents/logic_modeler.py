import json
import re
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from app.swarm.agents.base import BaseAgent
from app.config import settings

LOGIC_KEYWORDS = ["flow", "logic", "business", "checkout", "transfer", "auth", "role", "permission", "workflow", "trust"]

SYSTEM_PROMPT = """You are a security researcher mapping the business logic of a web application.
Given HTTP responses and discovered paths, identify user roles, trust boundaries, and workflows.
Return ONLY valid JSON with:
- user_roles: list of strings
- trust_boundaries: list of strings
- workflows: list of dicts with {name, steps: [string]}
- high_value_surfaces: list of strings (paths worth attacking for logic flaws)
"""


class LogicModelerAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2000,
        )

    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        text = f"{task.get('title', '')} {task.get('surface', '')}".lower()
        matches = sum(1 for kw in LOGIC_KEYWORDS if kw in text)
        confidence = min(0.92, 0.55 + matches * 0.08)
        return confidence, f"Logic modeler — {matches} business logic keyword matches", 8, "low"

    async def _execute(self, task: dict) -> dict:
        surface = task.get("surface", "")
        paths = []
        responses = {}
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(surface if surface.startswith("http") else f"https://{surface}")
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp.text)
                paths = list(set(h for h in hrefs if h.startswith("/")))[:20]
                responses[surface] = {"status": resp.status_code, "length": len(resp.text)}
        except Exception:
            pass
        try:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"Surface: {surface}\nPaths: {json.dumps(paths)}\nResponses: {json.dumps(responses)}"),
            ]
            response = await self._llm.ainvoke(messages)
            text = response.content.strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            logic_model = json.loads(text)
            self.emit_signal(0.8)
        except Exception:
            logic_model = {}
            self.emit_signal(0.3)
        return {"agent_type": "logic_modeler", "surface": surface, "logic_model": logic_model, "findings": []}
