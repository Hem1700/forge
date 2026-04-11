# backend/app/swarm/agents/base.py
import uuid
from enum import Enum
from dataclasses import dataclass, field
from app.config import settings


class AgentState(str, Enum):
    IDLE = "idle"
    BIDDING = "bidding"
    RUNNING = "running"
    TERMINATED = "terminated"
    COMPLETED = "completed"


@dataclass
class BaseAgent:
    agent_id: str
    engagement_id: str
    agent_type: str
    tools: list[str]
    parent_id: str | None = None
    spawned_reason: str = ""
    state: AgentState = AgentState.IDLE
    signal_history: list[float] = field(default_factory=list)
    termination_reason: str | None = None
    _window: int = field(default=5, init=False, repr=False)

    def emit_signal(self, score: float) -> None:
        self.signal_history.append(max(0.0, min(1.0, score)))

    def rolling_signal_average(self) -> float:
        if not self.signal_history:
            return 1.0
        window = self.signal_history[-self._window:]
        return sum(window) / len(window)

    def is_dead(self) -> bool:
        if len(self.signal_history) < settings.thread_death_threshold:
            return False
        recent = self.signal_history[-settings.thread_death_threshold:]
        return all(s < 0.2 for s in recent)

    def terminate(self, reason: str) -> None:
        self.state = AgentState.TERMINATED
        self.termination_reason = reason

    def complete(self) -> None:
        self.state = AgentState.COMPLETED

    async def bid(self, task: dict) -> dict:
        self.state = AgentState.BIDDING
        confidence, basis, probes, noise = await self._compute_confidence(task)
        return {
            "agent_id": self.agent_id,
            "confidence": confidence,
            "basis": basis,
            "estimated_probes": probes,
            "noise_level": noise,
        }

    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        return 0.5, "default base agent", 5, "medium"

    async def run(self, task: dict) -> dict:
        self.state = AgentState.RUNNING
        result = await self._execute(task)
        self.state = AgentState.COMPLETED
        return result

    async def _execute(self, task: dict) -> dict:
        return {"agent_type": self.agent_type, "surface": task.get("surface", ""), "findings": []}

    def spawn_child(self, reason: str, tools: list[str] | None = None) -> "BaseAgent":
        from app.swarm.agents.child import ChildAgent
        child = ChildAgent(
            agent_id=str(uuid.uuid4()),
            engagement_id=self.engagement_id,
            agent_type="child",
            tools=tools or self.tools,
            parent_id=self.agent_id,
            spawned_reason=reason,
        )
        return child
