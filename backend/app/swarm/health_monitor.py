import asyncio
import structlog
from app.swarm.scheduler import SwarmScheduler
from app.swarm.agents.base import AgentState

log = structlog.get_logger()


class HealthMonitor:
    def __init__(self, scheduler: SwarmScheduler, poll_interval: float = 10.0):
        self._scheduler = scheduler
        self._poll_interval = poll_interval
        self._running = False

    async def check_and_purge(self) -> list[str]:
        terminated = []
        for agent_id, agent in list(self._scheduler.agents.items()):
            if agent.state != AgentState.RUNNING:
                continue
            if agent.is_dead():
                agent.terminate("signal_below_threshold_for_5_consecutive_actions")
                log.info("agent_terminated", agent_id=agent_id, reason=agent.termination_reason)
                terminated.append(agent_id)
        return terminated

    async def start(self) -> None:
        self._running = True
        while self._running:
            terminated = await self.check_and_purge()
            if terminated:
                log.info("health_monitor_purged", count=len(terminated))
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
