# backend/app/swarm/agents/probe.py
from dataclasses import dataclass, field
from app.swarm.agents.base import BaseAgent
from app.brain.agent_brain import AgentBrain
from app.brain.agent_tools import HttpRequestTool, ExtractPatternTool, SubprocessTool

PROBE_KEYWORDS = {"sqli", "xss", "idor", "auth_bypass", "race_condition"}

PROBE_SYSTEM_PROMPT = (
    "You are a vulnerability prober. You receive a specific attack hypothesis. "
    "Test it with targeted payloads, vary your approach based on responses, and "
    "determine with high confidence whether the vulnerability exists. "
    "Report confirmed findings with evidence."
)


@dataclass
class ProbeAgent(BaseAgent):
    brain: AgentBrain = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self.brain = AgentBrain(
            system_prompt=PROBE_SYSTEM_PROMPT,
            tools=[HttpRequestTool(), ExtractPatternTool(), SubprocessTool()],
        )

    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        attack_class = task.get("attack_class", task.get("description", "")).lower()
        has_payloads = any(kw in attack_class for kw in PROBE_KEYWORDS)
        confidence = 0.75 if has_payloads else 0.55
        return (
            confidence,
            f"Probe agent — {'has' if has_payloads else 'no'} specific payloads for attack class",
            6,
            "low",
        )

    async def _execute(self, task: dict) -> dict:
        hypothesis = task.get("hypothesis", task)
        context = task.get("context", {"target_url": task.get("surface", "")})
        result = await self.brain.run(
            hypothesis, context,
            engagement_id=self.engagement_id, agent_id=self.agent_id, agent_type=self.agent_type,
        )
        return {
            "agent_type": "probe",
            "surface": task.get("surface", ""),
            "attack_class": task.get("attack_class", ""),
            "findings": result.findings,
            "confidence": result.confidence,
        }
