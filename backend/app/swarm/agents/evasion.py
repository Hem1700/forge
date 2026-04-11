import httpx
from app.swarm.agents.base import BaseAgent

EVASION_KEYWORDS = ["waf", "firewall", "rate limit", "fingerprint", "defense", "evasion", "bypass", "detect"]


class EvasionAgent(BaseAgent):
    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        text = f"{task.get('title', '')} {task.get('surface', '')}".lower()
        matches = sum(1 for kw in EVASION_KEYWORDS if kw in text)
        confidence = min(0.90, 0.60 + matches * 0.1)
        return confidence, f"Evasion specialist — {matches} defense keyword matches", 5, "low"

    async def _execute(self, task: dict) -> dict:
        surface = task.get("surface", "")
        url = surface if surface.startswith("http") else f"https://{surface}"
        waf_signals = []
        rate_limit_detected = False
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(url)
                headers = dict(resp.headers)
                waf_headers = ["cf-ray", "x-sucuri-id", "x-akamai", "x-waf", "x-firewall"]
                for h in waf_headers:
                    if h in {k.lower() for k in headers}:
                        waf_signals.append(h)
                responses = []
                for _ in range(5):
                    r = await client.get(url)
                    responses.append(r.status_code)
                if 429 in responses:
                    rate_limit_detected = True
                self.emit_signal(0.8)
        except Exception as e:
            self.emit_signal(0.2)
            return {"agent_type": "evasion", "surface": surface, "error": str(e), "findings": []}
        guidelines = []
        if waf_signals:
            guidelines.append("Use chunked transfer encoding to bypass body inspection")
            guidelines.append("Rotate User-Agent and X-Forwarded-For headers")
        if rate_limit_detected:
            guidelines.append("Space requests at least 200ms apart")
        return {"agent_type": "evasion", "surface": surface, "waf_signals": waf_signals, "rate_limit_detected": rate_limit_detected, "guidelines": guidelines, "findings": [{"type": "evasion_profile", "waf": bool(waf_signals), "rate_limit": rate_limit_detected}]}
