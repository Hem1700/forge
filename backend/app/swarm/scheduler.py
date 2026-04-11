from app.swarm.agents.base import BaseAgent, AgentState
from app.swarm.task_board import TaskBoard
from app.config import settings


class SwarmScheduler:
    def __init__(self, engagement_id: str):
        self.engagement_id = engagement_id
        self.agents: dict[str, BaseAgent] = {}
        self._task_board = TaskBoard()
        self._running = False

    def register_agent(self, agent: BaseAgent) -> None:
        self.agents[agent.agent_id] = agent

    def deregister_agent(self, agent_id: str) -> None:
        self.agents.pop(agent_id, None)

    def get_lineage(self, agent_id: str) -> list[str]:
        children = []
        for aid, agent in self.agents.items():
            if agent.parent_id == agent_id:
                children.append(aid)
                children.extend(self.get_lineage(aid))
        return children

    def get_available_agents(self) -> list[BaseAgent]:
        return [a for a in self.agents.values() if a.state == AgentState.IDLE]

    async def run_auction(self, task: dict) -> BaseAgent | None:
        available = self.get_available_agents()
        if not available:
            return None
        required_confidence = float(task.get("required_confidence", 0.6))
        bids = []
        for agent in available:
            bid = await agent.bid(task)
            if bid["confidence"] >= required_confidence:
                bids.append((agent, bid))
        if not bids:
            return None
        noise_order = {"low": 0, "medium": 1, "high": 2}
        bids.sort(key=lambda x: (-x[1]["confidence"], noise_order.get(x[1]["noise_level"], 1)))
        winner, _ = bids[0]
        return winner

    async def assign_and_run(self, task: dict) -> dict | None:
        winner = await self.run_auction(task)
        if winner is None:
            return None
        await self._task_board.assign_task(task["task_id"], winner.agent_id)
        return await winner.run(task)

    async def purge_dead_agents(self) -> list[str]:
        terminated = []
        for agent_id, agent in list(self.agents.items()):
            if agent.state == AgentState.RUNNING and agent.is_dead():
                agent.terminate("signal_too_low")
                terminated.append(agent_id)
        return terminated

    def active_count(self) -> int:
        return sum(1 for a in self.agents.values() if a.state in (AgentState.IDLE, AgentState.RUNNING, AgentState.BIDDING))
