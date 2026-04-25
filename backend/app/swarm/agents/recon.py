# backend/app/swarm/agents/recon.py
from dataclasses import dataclass, field
from app.swarm.agents.base import BaseAgent
from app.brain.agent_brain import AgentBrain
from app.brain.agent_tools import HttpRequestTool, ExtractPatternTool, SubprocessTool

RECON_KEYWORDS = ["recon", "subdomain", "endpoint", "discovery", "fingerprint", "enum", "crawl", "scan", "map"]

RECON_SYSTEM_PROMPT = (
    "You are a recon specialist. Your goal is to map the attack surface: "
    "discover endpoints, identify technologies and frameworks, enumerate parameters, "
    "surface authentication boundaries. Do NOT exploit — your job is to produce a "
    "comprehensive target map for probe agents. Report everything unusual."
)


@dataclass
class ReconAgent(BaseAgent):
    brain: AgentBrain = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.brain = AgentBrain(
            system_prompt=RECON_SYSTEM_PROMPT,
            tools=[HttpRequestTool(), ExtractPatternTool(), SubprocessTool()],
        )

    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        text = f"{task.get('title', '')} {task.get('surface', '')}".lower()
        matches = sum(1 for kw in RECON_KEYWORDS if kw in text)
        confidence = min(0.95, 0.5 + matches * 0.1)
        return confidence, f"Recon specialist — {matches} keyword matches", 3, "low"

    async def _execute(self, task: dict) -> dict:
        hypothesis = task.get("hypothesis", task)
        context = task.get("context", {"target_url": task.get("surface", "")})
        result = await self.brain.run(
            hypothesis, context,
            engagement_id=self.engagement_id, agent_id=self.agent_id, agent_type=self.agent_type,
        )
        return {
            "agent_type": "recon",
            "surface": task.get("surface", ""),
            "findings": result.findings,
            "confidence": result.confidence,
        }
