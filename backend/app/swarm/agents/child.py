import httpx
from app.swarm.agents.base import BaseAgent

class ChildAgent(BaseAgent):
    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        return 0.6, "Child agent — following parent thread", 3, "low"

    async def _execute(self, task: dict) -> dict:
        surface = task.get("surface", "")
        result = {"agent_type": "child", "surface": surface, "findings": []}
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(surface if surface.startswith("http") else f"https://{surface}")
                self.emit_signal(0.6 if resp.status_code < 400 else 0.2)
                result["status_code"] = resp.status_code
                result["findings"].append({"type": "probe", "status": resp.status_code})
        except Exception as e:
            self.emit_signal(0.1)
            result["findings"].append({"type": "error", "message": str(e)})
        return result
