# backend/app/brain/semantic_modeler.py
import json
import re
import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from app.brain.llm_factory import get_llm, TaskType


SYSTEM_PROMPT = """You are a security researcher analyzing a web application.
Given crawl data about a target application, produce a structured semantic model of what the app does.

Return ONLY valid JSON with these fields:
- app_type: string (saas, ecommerce, fintech, api-only, cms, social, other)
- tech_stack: list of strings (detected technologies)
- endpoints: list of strings (discovered API/page paths)
- user_roles: list of strings (inferred user roles)
- business_flows: list of strings (key workflows)
- trust_boundaries: list of strings (auth levels/access tiers)
- interesting_surfaces: list of strings (highest-value attack surfaces)
"""


class SemanticModeler:
    def __init__(self, org_id=None):
        self._org_id = org_id

    async def crawl(self, target_url: str) -> dict:
        """Lightweight passive crawl — just headers and a homepage fetch."""
        paths = []
        headers = {}
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(target_url)
                headers = dict(resp.headers)
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp.text)
                paths = list(set(h for h in hrefs if h.startswith("/")))[:50]
        except Exception:
            pass
        return {"paths": paths, "headers": headers, "base_url": target_url}

    async def build(self, target_url: str, crawl_data: dict) -> dict:
        """Build semantic app model from crawl data using LLM reasoning."""
        user_content = f"""
Target URL: {target_url}

Discovered paths: {json.dumps(crawl_data.get('paths', [])[:30])}
Response headers: {json.dumps({k: v for k, v in crawl_data.get('headers', {}).items() if k.lower() in ['server', 'x-powered-by', 'x-framework', 'content-type', 'set-cookie']})}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        llm = await get_llm(TaskType.semantic_modeler, org_id=self._org_id)
        response = await llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
