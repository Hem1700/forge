# backend/app/swarm/task_board.py
import json
import uuid
from datetime import datetime, timezone
import redis.asyncio as aioredis
from app.config import settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskBoard:
    """
    Redis-backed task board. Uses Redis hashes for task state and
    Redis lists for bids. Every mutation appends to an event stream.
    """

    def __init__(self, redis_url: str = None):
        self._redis_url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _task_key(self, task_id: str) -> str:
        return f"forge:task:{task_id}"

    def _bid_key(self, task_id: str) -> str:
        return f"forge:bids:{task_id}"

    def _engagement_tasks_key(self, engagement_id: str) -> str:
        return f"forge:engagement:{engagement_id}:tasks"

    async def publish_task(
        self,
        task_id: str,
        engagement_id: str,
        title: str,
        surface: str,
        required_confidence: float,
        priority: str,
        created_by: str,
        description: str = "",
        hypothesis_id: str | None = None,
    ) -> None:
        r = await self._get_redis()
        now = _now_iso()
        task_data = {
            "task_id": task_id,
            "engagement_id": engagement_id,
            "title": title,
            "description": description,
            "surface": surface,
            "required_confidence": str(required_confidence),
            "priority": priority,
            "status": "open",
            "created_by": created_by,
            "assigned_agent_id": "",
            "hypothesis_id": hypothesis_id or "",
            "created_at": now,
            "event_log": json.dumps([{"event": "created", "at": now}]),
        }
        await r.hset(self._task_key(task_id), mapping=task_data)
        await r.sadd(self._engagement_tasks_key(engagement_id), task_id)

    async def get_task(self, task_id: str) -> dict | None:
        r = await self._get_redis()
        data = await r.hgetall(self._task_key(task_id))
        if not data:
            return None
        data["required_confidence"] = float(data["required_confidence"])
        data["event_log"] = json.loads(data.get("event_log", "[]"))
        return data

    async def get_open_tasks(self, engagement_id: str) -> list[dict]:
        r = await self._get_redis()
        task_ids = await r.smembers(self._engagement_tasks_key(engagement_id))
        tasks = []
        for tid in task_ids:
            task = await self.get_task(tid)
            if task and task["status"] == "open":
                tasks.append(task)
        return tasks

    async def submit_bid(
        self,
        task_id: str,
        agent_id: str,
        confidence: float,
        basis: str,
        estimated_probes: int,
        noise_level: str,
    ) -> None:
        r = await self._get_redis()
        bid = {
            "bid_id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "confidence": confidence,
            "basis": basis,
            "estimated_probes": estimated_probes,
            "noise_level": noise_level,
            "submitted_at": _now_iso(),
        }
        await r.rpush(self._bid_key(task_id), json.dumps(bid))
        await r.hset(self._task_key(task_id), "status", "bidding")

    async def get_bids(self, task_id: str) -> list[dict]:
        r = await self._get_redis()
        raw_bids = await r.lrange(self._bid_key(task_id), 0, -1)
        return [json.loads(b) for b in raw_bids]

    async def assign_task(self, task_id: str, agent_id: str) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), mapping={
            "status": "assigned",
            "assigned_agent_id": agent_id,
        })
        task = await self.get_task(task_id)
        log = task.get("event_log", [])
        log.append({"event": "assigned", "agent_id": agent_id, "at": _now_iso()})
        await r.hset(self._task_key(task_id), "event_log", json.dumps(log))

    async def complete_task(self, task_id: str, result: dict) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), mapping={
            "status": "complete",
            "result": json.dumps(result),
        })

    async def reject_task(self, task_id: str, reason: str) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), mapping={
            "status": "rejected",
            "result": json.dumps({"reason": reason}),
        })

    async def gate_task(self, task_id: str) -> None:
        r = await self._get_redis()
        await r.hset(self._task_key(task_id), "status", "awaiting_human_gate")
