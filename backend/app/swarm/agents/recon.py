import httpx
import re
from app.swarm.agents.base import BaseAgent

RECON_KEYWORDS = ["recon", "subdomain", "endpoint", "discovery", "fingerprint", "enum", "crawl", "scan", "map"]

class ReconAgent(BaseAgent):
    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        text = f"{task.get('title', '')} {task.get('surface', '')}".lower()
        matches = sum(1 for kw in RECON_KEYWORDS if kw in text)
        confidence = min(0.95, 0.5 + matches * 0.1)
        return confidence, f"Recon specialist — {matches} keyword matches", 3, "low"

    async def _execute(self, task: dict) -> dict:
        surface = task.get("surface", "")
        findings = []
        paths_found = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(surface if surface.startswith("http") else f"https://{surface}")
                server = resp.headers.get("server", "unknown")
                powered_by = resp.headers.get("x-powered-by", "")
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp.text)
                paths_found = list(set(h for h in hrefs if h.startswith("/")))[:30]
                self.emit_signal(0.7 if paths_found else 0.3)
                findings.append({"type": "fingerprint", "server": server, "x_powered_by": powered_by})
        except Exception as e:
            self.emit_signal(0.1)
            findings.append({"type": "error", "message": str(e)})
        return {"agent_type": "recon", "surface": surface, "paths": paths_found, "findings": findings}
