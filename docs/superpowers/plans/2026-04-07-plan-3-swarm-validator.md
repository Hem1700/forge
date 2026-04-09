# FORGE Plan 3: Tactical Swarm + Adversarial Validator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build all 6 agent types, the Swarm Scheduler (bidding auction + lineage tracking), the Thread Health Monitor, and the full 4-stage Adversarial Validator pipeline.

**Architecture:** All agents extend a `BaseAgent` that owns the bid/run/terminate lifecycle. The Swarm Scheduler runs a continuous loop consuming the Task Board, running bid auctions, and tracking lineage. The Health Monitor emits signal scores and terminates dead threads. The Validator is a 4-stage pipeline (Challenger → Context → Severity → Scorer) that every finding must pass before reaching a human gate.

**Tech Stack:** LangGraph for stateful agent graphs, LangChain, httpx, playwright, pwntools (optional), Redis, PostgreSQL, pytest-asyncio

**Prerequisite:** Plans 1 and 2 complete.

---

## File Map

| File | Purpose |
|---|---|
| `backend/app/swarm/agents/base.py` | BaseAgent — bid, run, terminate, spawn_child lifecycle |
| `backend/app/swarm/agents/recon.py` | ReconAgent — surface discovery, tech fingerprinting |
| `backend/app/swarm/agents/logic_modeler.py` | LogicModelerAgent — behavioral crawl, trust model |
| `backend/app/swarm/agents/probe.py` | ProbeAgent — single hypothesis test, minimal noise |
| `backend/app/swarm/agents/evasion.py` | EvasionAgent — models defensive stack, advises swarm |
| `backend/app/swarm/agents/deep_exploit.py` | DeepExploitAgent — full exploit chain, post-gate only |
| `backend/app/swarm/agents/child.py` | ChildAgent — generic sub-thread spawned by any agent |
| `backend/app/swarm/scheduler.py` | Swarm Scheduler — auction loop, lineage, allocation |
| `backend/app/swarm/health_monitor.py` | Thread Health Monitor — signal tracking, termination |
| `backend/app/validator/challenger.py` | Challenger — independent reproduction of finding |
| `backend/app/validator/context.py` | Context — scope check, false positive patterns |
| `backend/app/validator/severity.py` | Severity — CVSS + business context scoring |
| `backend/app/validator/scorer.py` | Confidence Scorer — final 0–1 score, gate threshold |
| `backend/tests/test_agents.py` | Agent lifecycle + bid tests |
| `backend/tests/test_scheduler.py` | Scheduler auction + lineage tests |
| `backend/tests/test_validator.py` | Full validator pipeline tests |

---

### Task 1: Base Agent

**Files:**
- Create: `backend/app/swarm/agents/base.py`
- Test: `backend/tests/test_agents.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_agents.py
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from app.swarm.agents.base import BaseAgent, AgentState


def make_agent(agent_type="probe"):
    return BaseAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type=agent_type,
        tools=[],
    )


def test_agent_initial_state():
    agent = make_agent()
    assert agent.state == AgentState.IDLE
    assert agent.signal_history == []
    assert agent.parent_id is None


def test_agent_emit_signal_tracks_history():
    agent = make_agent()
    agent.emit_signal(0.9)
    agent.emit_signal(0.1)
    agent.emit_signal(0.2)
    assert len(agent.signal_history) == 3
    assert agent.signal_history[0] == 0.9


def test_agent_is_dead_when_signals_too_low():
    agent = make_agent()
    for _ in range(5):
        agent.emit_signal(0.1)
    assert agent.is_dead() is True


def test_agent_not_dead_with_mixed_signals():
    agent = make_agent()
    for _ in range(4):
        agent.emit_signal(0.1)
    agent.emit_signal(0.9)
    assert agent.is_dead() is False


def test_agent_rolling_average():
    agent = make_agent()
    for _ in range(10):
        agent.emit_signal(0.1)
    agent.emit_signal(0.9)
    # rolling window is last 5 — [0.1, 0.1, 0.1, 0.1, 0.9] avg = 0.26
    assert agent.rolling_signal_average() > 0.2


@pytest.mark.asyncio
async def test_agent_bid_returns_bid_dict():
    agent = make_agent()
    task = {
        "task_id": str(uuid.uuid4()),
        "title": "Test JWT bypass",
        "surface": "/api/auth",
        "required_confidence": 0.7,
        "priority": "high",
    }
    bid = await agent.bid(task)
    assert "confidence" in bid
    assert "basis" in bid
    assert "noise_level" in bid
    assert 0.0 <= bid["confidence"] <= 1.0
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_agents.py -v
# Expected: ImportError
```

- [ ] **Step 3: Implement base.py**

```python
# backend/app/swarm/agents/base.py
import uuid
from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from app.config import settings


class AgentState(str, Enum):
    IDLE = "idle"
    BIDDING = "bidding"
    RUNNING = "running"
    TERMINATED = "terminated"
    COMPLETED = "completed"


@dataclass
class BaseAgent(ABC):
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
        """Record a signal score (0=dead end, 1=very promising)."""
        self.signal_history.append(max(0.0, min(1.0, score)))

    def rolling_signal_average(self) -> float:
        if not self.signal_history:
            return 1.0
        window = self.signal_history[-self._window:]
        return sum(window) / len(window)

    def is_dead(self) -> bool:
        """True if the last N signals are all below the death threshold."""
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
        """
        Evaluate a task and return a bid dict.
        Subclasses override _compute_confidence for domain-specific scoring.
        """
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
        """Override in subclasses. Returns (confidence, basis, est_probes, noise_level)."""
        return 0.5, "default base agent", 5, "medium"

    async def run(self, task: dict) -> dict:
        """Execute the task. Must be implemented by subclasses."""
        self.state = AgentState.RUNNING
        result = await self._execute(task)
        self.state = AgentState.COMPLETED
        return result

    @abstractmethod
    async def _execute(self, task: dict) -> dict:
        """Subclass implements actual task execution logic."""
        ...

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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_agents.py -v
# Expected: 6 PASSED (bid test may fail — fix after ChildAgent exists)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/swarm/agents/base.py backend/tests/test_agents.py
git commit -m "feat: BaseAgent with signal tracking, dead detection, bid lifecycle"
```

---

### Task 2: Recon + Child Agents

**Files:**
- Create: `backend/app/swarm/agents/recon.py`
- Create: `backend/app/swarm/agents/child.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_agents.py
from app.swarm.agents.recon import ReconAgent
from app.swarm.agents.child import ChildAgent


@pytest.mark.asyncio
async def test_recon_agent_bids_high_on_recon_tasks():
    agent = ReconAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type="recon",
        tools=["httpx", "subfinder"],
    )
    task = {"task_id": str(uuid.uuid4()), "title": "Subdomain enumeration", "surface": "example.com", "required_confidence": 0.5, "priority": "high"}
    bid = await agent.bid(task)
    assert bid["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_child_agent_inherits_parent():
    parent = ReconAgent(
        agent_id="parent-001",
        engagement_id=str(uuid.uuid4()),
        agent_type="recon",
        tools=["httpx"],
    )
    child = parent.spawn_child(reason="Found JS bundle, needs analysis", tools=["js_analyzer"])
    assert child.parent_id == "parent-001"
    assert child.spawned_reason == "Found JS bundle, needs analysis"
    assert "js_analyzer" in child.tools
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_agents.py::test_recon_agent_bids_high_on_recon_tasks -v
# Expected: ImportError
```

- [ ] **Step 3: Implement recon.py**

```python
# backend/app/swarm/agents/recon.py
import httpx
import re
from app.swarm.agents.base import BaseAgent


RECON_KEYWORDS = ["recon", "subdomain", "endpoint", "discovery", "fingerprint", "enum", "crawl", "scan", "map"]


class ReconAgent(BaseAgent):
    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        title_lower = task.get("title", "").lower()
        surface_lower = task.get("surface", "").lower()
        text = f"{title_lower} {surface_lower}"
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
```

- [ ] **Step 4: Implement child.py**

```python
# backend/app/swarm/agents/child.py
from app.swarm.agents.base import BaseAgent
import httpx


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
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_agents.py -v
# Expected: 8 PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/swarm/agents/recon.py backend/app/swarm/agents/child.py
git commit -m "feat: ReconAgent and ChildAgent with bid scoring and execution"
```

---

### Task 3: Logic Modeler + Probe Agents

**Files:**
- Create: `backend/app/swarm/agents/logic_modeler.py`
- Create: `backend/app/swarm/agents/probe.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_agents.py
from app.swarm.agents.logic_modeler import LogicModelerAgent
from app.swarm.agents.probe import ProbeAgent


@pytest.mark.asyncio
async def test_logic_modeler_bids_on_business_flow_tasks():
    agent = LogicModelerAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type="logic_modeler",
        tools=["playwright"],
    )
    task = {"task_id": str(uuid.uuid4()), "title": "Map checkout business flow", "surface": "/checkout", "required_confidence": 0.5, "priority": "high"}
    bid = await agent.bid(task)
    assert bid["confidence"] >= 0.6


@pytest.mark.asyncio
async def test_probe_agent_execute_returns_result():
    agent = ProbeAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type="probe",
        tools=["httpx"],
    )
    task = {
        "task_id": str(uuid.uuid4()),
        "title": "Test IDOR on /api/users/1",
        "surface": "https://httpbin.org/get",
        "required_confidence": 0.6,
        "priority": "high",
        "description": "Check if user ID 1 returns data for unauthenticated request",
    }
    result = await agent.run(task)
    assert "findings" in result
    assert isinstance(result["findings"], list)
```

- [ ] **Step 2: Run — verify they fail**

```bash
cd backend && pytest tests/test_agents.py::test_logic_modeler_bids_on_business_flow_tasks -v
# Expected: ImportError
```

- [ ] **Step 3: Implement logic_modeler.py**

```python
# backend/app/swarm/agents/logic_modeler.py
import json
import re
import httpx
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.swarm.agents.base import BaseAgent
from app.config import settings


LOGIC_KEYWORDS = ["flow", "logic", "business", "checkout", "transfer", "auth", "role", "permission", "workflow", "trust"]

SYSTEM_PROMPT = """You are a security researcher mapping the business logic of a web application.
Given HTTP responses and discovered paths, identify user roles, trust boundaries, and workflows.
Return ONLY valid JSON with:
- user_roles: list of strings
- trust_boundaries: list of strings  
- workflows: list of dicts with {name, steps: [string]}
- high_value_surfaces: list of strings (paths worth attacking for logic flaws)
"""


class LogicModelerAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=2000,
        )

    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        text = f"{task.get('title', '')} {task.get('surface', '')}".lower()
        matches = sum(1 for kw in LOGIC_KEYWORDS if kw in text)
        confidence = min(0.92, 0.55 + matches * 0.08)
        return confidence, f"Logic modeler — {matches} business logic keyword matches", 8, "low"

    async def _execute(self, task: dict) -> dict:
        surface = task.get("surface", "")
        paths = []
        responses = {}
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(surface if surface.startswith("http") else f"https://{surface}")
                hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp.text)
                paths = list(set(h for h in hrefs if h.startswith("/")))[:20]
                responses[surface] = {"status": resp.status_code, "length": len(resp.text)}
        except Exception:
            pass

        try:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"Surface: {surface}\nPaths: {json.dumps(paths)}\nResponses: {json.dumps(responses)}"),
            ]
            response = await self._llm.ainvoke(messages)
            text = response.content.strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            logic_model = json.loads(text)
            self.emit_signal(0.8)
        except Exception:
            logic_model = {}
            self.emit_signal(0.3)

        return {"agent_type": "logic_modeler", "surface": surface, "logic_model": logic_model, "findings": []}
```

- [ ] **Step 4: Implement probe.py**

```python
# backend/app/swarm/agents/probe.py
import httpx
import re
from app.swarm.agents.base import BaseAgent


# Common probe payloads keyed by attack class
PROBE_PAYLOADS = {
    "sqli": ["'", "1' OR '1'='1", "1; DROP TABLE users--"],
    "xss": ["<script>alert(1)</script>", '"><img src=x onerror=alert(1)>'],
    "idor": ["/1", "/2", "/0", "/../admin"],
    "auth_bypass": ["../", "..%2f", "%00"],
    "race_condition": [],  # handled via concurrent requests
    "default": ["test", "probe"],
}


class ProbeAgent(BaseAgent):
    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        attack_class = task.get("attack_class", task.get("description", "")).lower()
        has_payloads = any(kw in attack_class for kw in PROBE_PAYLOADS)
        confidence = 0.75 if has_payloads else 0.55
        return confidence, f"Probe agent — {'has' if has_payloads else 'no'} specific payloads for attack class", 6, "low"

    async def _execute(self, task: dict) -> dict:
        surface = task.get("surface", "")
        description = task.get("description", "")
        attack_class = task.get("attack_class", "default")
        payloads = PROBE_PAYLOADS.get(attack_class, PROBE_PAYLOADS["default"])
        findings = []
        base_url = surface if surface.startswith("http") else f"https://{surface}"

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
                # baseline request
                baseline = await client.get(base_url)
                baseline_len = len(baseline.text)
                baseline_status = baseline.status_code

                for payload in payloads[:3]:
                    try:
                        test_url = f"{base_url}?q={payload}"
                        resp = await client.get(test_url)
                        length_diff = abs(len(resp.text) - baseline_len)
                        status_diff = resp.status_code != baseline_status
                        error_keywords = any(kw in resp.text.lower() for kw in ["error", "exception", "syntax", "warning", "stack trace"])

                        if error_keywords or status_diff or length_diff > 500:
                            findings.append({
                                "type": "anomaly",
                                "payload": payload,
                                "status": resp.status_code,
                                "length_diff": length_diff,
                                "error_keywords": error_keywords,
                            })
                            self.emit_signal(0.8)
                        else:
                            self.emit_signal(0.2)
                    except Exception:
                        self.emit_signal(0.1)

        except Exception as e:
            self.emit_signal(0.0)
            findings.append({"type": "error", "message": str(e)})

        signal = 0.9 if findings else 0.1
        self.emit_signal(signal)
        return {
            "agent_type": "probe",
            "surface": surface,
            "attack_class": attack_class,
            "findings": findings,
            "anomalies_found": len(findings),
        }
```

- [ ] **Step 5: Run all agent tests — verify they pass**

```bash
cd backend && pytest tests/test_agents.py -v
# Expected: 10 PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/swarm/agents/logic_modeler.py backend/app/swarm/agents/probe.py
git commit -m "feat: LogicModelerAgent (LLM business flow mapping) and ProbeAgent (payload testing)"
```

---

### Task 4: Evasion + Deep Exploit Agents

**Files:**
- Create: `backend/app/swarm/agents/evasion.py`
- Create: `backend/app/swarm/agents/deep_exploit.py`
- Test: `backend/tests/test_agents.py` (append)

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_agents.py
from app.swarm.agents.evasion import EvasionAgent
from app.swarm.agents.deep_exploit import DeepExploitAgent


@pytest.mark.asyncio
async def test_evasion_agent_bids_on_defense_tasks():
    agent = EvasionAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type="evasion",
        tools=["httpx"],
    )
    task = {"task_id": str(uuid.uuid4()), "title": "Fingerprint WAF and rate limits", "surface": "https://example.com", "required_confidence": 0.5, "priority": "medium"}
    bid = await agent.bid(task)
    assert bid["confidence"] >= 0.6
    assert bid["noise_level"] == "low"


def test_deep_exploit_agent_requires_gate_approval():
    agent = DeepExploitAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type="deep_exploit",
        tools=["httpx"],
        gate_approved=False,
    )
    assert agent.gate_approved is False
```

- [ ] **Step 2: Run — verify they fail**

```bash
cd backend && pytest tests/test_agents.py::test_evasion_agent_bids_on_defense_tasks -v
# Expected: ImportError
```

- [ ] **Step 3: Implement evasion.py**

```python
# backend/app/swarm/agents/evasion.py
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

                # probe for rate limiting
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
            guidelines.append("Use multiple source IPs if available")

        return {
            "agent_type": "evasion",
            "surface": surface,
            "waf_signals": waf_signals,
            "rate_limit_detected": rate_limit_detected,
            "guidelines": guidelines,
            "findings": [{"type": "evasion_profile", "waf": bool(waf_signals), "rate_limit": rate_limit_detected}],
        }
```

- [ ] **Step 4: Implement deep_exploit.py**

```python
# backend/app/swarm/agents/deep_exploit.py
import httpx
from dataclasses import dataclass, field
from app.swarm.agents.base import BaseAgent, AgentState


@dataclass
class DeepExploitAgent(BaseAgent):
    gate_approved: bool = False

    async def _compute_confidence(self, task: dict) -> tuple[float, str, int, str]:
        if not self.gate_approved:
            return 0.0, "Gate approval required before deep exploitation", 0, "high"
        return 0.85, "Deep exploit agent — full chain execution", 15, "high"

    async def _execute(self, task: dict) -> dict:
        if not self.gate_approved:
            self.terminate("Gate approval not received")
            return {"agent_type": "deep_exploit", "error": "Requires human gate approval", "findings": []}

        surface = task.get("surface", "")
        attack_class = task.get("attack_class", "")
        findings = []

        # Deep exploitation logic varies by attack class.
        # This is the skeleton — full payload chains are added per attack class.
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(surface if surface.startswith("http") else f"https://{surface}")
                # In a real implementation, this is where full exploit chains execute.
                # Placeholder: document the confirmed vulnerability surface.
                self.emit_signal(0.9)
                findings.append({
                    "type": "confirmed_vuln",
                    "surface": surface,
                    "attack_class": attack_class,
                    "status_code": resp.status_code,
                    "evidence": f"Response length: {len(resp.text)}",
                    "reproduction": [f"GET {surface}", f"Payload: {attack_class} exploit chain"],
                })
        except Exception as e:
            self.emit_signal(0.1)
            findings.append({"type": "error", "message": str(e)})

        return {"agent_type": "deep_exploit", "surface": surface, "attack_class": attack_class, "findings": findings}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_agents.py -v
# Expected: 12 PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/swarm/agents/evasion.py backend/app/swarm/agents/deep_exploit.py
git commit -m "feat: EvasionAgent (WAF/rate-limit fingerprinting) and DeepExploitAgent (gate-gated)"
```

---

### Task 5: Swarm Scheduler

**Files:**
- Create: `backend/app/swarm/scheduler.py`
- Test: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_scheduler.py
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from app.swarm.scheduler import SwarmScheduler
from app.swarm.agents.probe import ProbeAgent
from app.swarm.agents.recon import ReconAgent


@pytest.fixture
def scheduler():
    return SwarmScheduler(engagement_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_scheduler_registers_agent(scheduler):
    agent = ReconAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=scheduler.engagement_id,
        agent_type="recon",
        tools=[],
    )
    scheduler.register_agent(agent)
    assert agent.agent_id in scheduler.agents


@pytest.mark.asyncio
async def test_run_auction_assigns_highest_bidder(scheduler):
    task = {
        "task_id": str(uuid.uuid4()),
        "title": "Subdomain enumeration",
        "surface": "example.com",
        "required_confidence": 0.5,
        "priority": "high",
        "attack_class": "recon",
    }
    agent_low = ProbeAgent(agent_id="agent-low", engagement_id=scheduler.engagement_id, agent_type="probe", tools=[])
    agent_high = ReconAgent(agent_id="agent-high", engagement_id=scheduler.engagement_id, agent_type="recon", tools=[])
    scheduler.register_agent(agent_low)
    scheduler.register_agent(agent_high)

    winner = await scheduler.run_auction(task)
    assert winner is not None
    assert winner.agent_id == "agent-high"


@pytest.mark.asyncio
async def test_scheduler_tracks_lineage(scheduler):
    parent = ReconAgent(agent_id="parent-1", engagement_id=scheduler.engagement_id, agent_type="recon", tools=[])
    scheduler.register_agent(parent)
    child = parent.spawn_child("found something interesting")
    scheduler.register_agent(child)
    lineage = scheduler.get_lineage("parent-1")
    assert child.agent_id in lineage
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_scheduler.py -v
# Expected: ImportError
```

- [ ] **Step 3: Implement scheduler.py**

```python
# backend/app/swarm/scheduler.py
import asyncio
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
        """Return all child agent IDs spawned (directly or transitively) from agent_id."""
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

        # Sort by confidence desc, then noise level asc (low < medium < high)
        noise_order = {"low": 0, "medium": 1, "high": 2}
        bids.sort(key=lambda x: (-x[1]["confidence"], noise_order.get(x[1]["noise_level"], 1)))
        winner, winning_bid = bids[0]
        return winner

    async def assign_and_run(self, task: dict) -> dict | None:
        winner = await self.run_auction(task)
        if winner is None:
            return None
        await self._task_board.assign_task(task["task_id"], winner.agent_id)
        result = await winner.run(task)
        return result

    async def purge_dead_agents(self) -> list[str]:
        """Terminate agents whose signal history indicates dead threads."""
        terminated = []
        for agent_id, agent in list(self.agents.items()):
            if agent.state == AgentState.RUNNING and agent.is_dead():
                agent.terminate("signal_too_low")
                terminated.append(agent_id)
        return terminated

    def active_count(self) -> int:
        return sum(1 for a in self.agents.values() if a.state in (AgentState.IDLE, AgentState.RUNNING, AgentState.BIDDING))
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_scheduler.py -v
# Expected: 3 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/swarm/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat: SwarmScheduler with bid auction, lineage tracking, dead agent purge"
```

---

### Task 6: Thread Health Monitor

**Files:**
- Create: `backend/app/swarm/health_monitor.py`
- Test: `backend/tests/test_scheduler.py` (append)

- [ ] **Step 1: Add failing tests**

```python
# append to backend/tests/test_scheduler.py
from app.swarm.health_monitor import HealthMonitor
from app.swarm.agents.base import AgentState


@pytest.mark.asyncio
async def test_health_monitor_terminates_dead_agents():
    engagement_id = str(uuid.uuid4())
    agent = ProbeAgent(agent_id=str(uuid.uuid4()), engagement_id=engagement_id, agent_type="probe", tools=[])
    # Push it below death threshold
    for _ in range(6):
        agent.emit_signal(0.05)

    scheduler = SwarmScheduler(engagement_id=engagement_id)
    scheduler.register_agent(agent)
    # Manually set state to running so health monitor considers it
    agent.state = AgentState.RUNNING

    monitor = HealthMonitor(scheduler)
    terminated = await monitor.check_and_purge()
    assert agent.agent_id in terminated
    assert agent.state == AgentState.TERMINATED


@pytest.mark.asyncio
async def test_health_monitor_keeps_healthy_agents():
    engagement_id = str(uuid.uuid4())
    agent = ReconAgent(agent_id=str(uuid.uuid4()), engagement_id=engagement_id, agent_type="recon", tools=[])
    agent.emit_signal(0.9)
    agent.emit_signal(0.8)
    agent.state = AgentState.RUNNING

    scheduler = SwarmScheduler(engagement_id=engagement_id)
    scheduler.register_agent(agent)

    monitor = HealthMonitor(scheduler)
    terminated = await monitor.check_and_purge()
    assert agent.agent_id not in terminated
    assert agent.state == AgentState.RUNNING
```

- [ ] **Step 2: Run — verify they fail**

```bash
cd backend && pytest tests/test_scheduler.py::test_health_monitor_terminates_dead_agents -v
# Expected: ImportError
```

- [ ] **Step 3: Implement health_monitor.py**

```python
# backend/app/swarm/health_monitor.py
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
        """Check all running agents, terminate dead ones, return list of terminated IDs."""
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
        """Run health checks on a continuous loop until stopped."""
        self._running = True
        while self._running:
            terminated = await self.check_and_purge()
            if terminated:
                log.info("health_monitor_purged", count=len(terminated))
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
```

- [ ] **Step 4: Run all scheduler tests — verify they pass**

```bash
cd backend && pytest tests/test_scheduler.py -v
# Expected: 5 PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/swarm/health_monitor.py
git commit -m "feat: HealthMonitor — continuous signal-based agent termination"
```

---

### Task 7: Adversarial Validator Pipeline

**Files:**
- Create: `backend/app/validator/challenger.py`
- Create: `backend/app/validator/context.py`
- Create: `backend/app/validator/severity.py`
- Create: `backend/app/validator/scorer.py`
- Test: `backend/tests/test_validator.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_validator.py
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.validator.challenger import Challenger
from app.validator.context import ContextChecker
from app.validator.severity import SeverityAssessor
from app.validator.scorer import ConfidenceScorer


def make_finding():
    return {
        "id": str(uuid.uuid4()),
        "engagement_id": str(uuid.uuid4()),
        "title": "IDOR in /api/users/{id}",
        "vulnerability_class": "idor",
        "affected_surface": "https://example.com/api/users/2",
        "description": "Accessing /api/users/2 while authenticated as user 1 returns user 2 data",
        "reproduction_steps": [
            "Login as user1",
            "GET /api/users/2",
            "Response contains user2 PII"
        ],
        "evidence": [{"type": "http_trace", "request": "GET /api/users/2", "response_status": 200}],
        "severity": "high",
        "cvss_score": 7.5,
    }


@pytest.mark.asyncio
async def test_challenger_reproduces_finding():
    challenger = Challenger()
    finding = make_finding()
    mock_response = MagicMock()
    mock_response.content = '{"reproduced": true, "confidence": 0.88, "notes": "Confirmed IDOR - user 2 data returned without authorization"}'
    with patch.object(challenger._llm, "ainvoke", return_value=mock_response):
        result = await challenger.challenge(finding)
    assert result["reproduced"] is True
    assert result["confidence"] >= 0.8


@pytest.mark.asyncio
async def test_context_checker_passes_in_scope():
    checker = ContextChecker()
    finding = make_finding()
    scope = ["example.com", "api.example.com"]
    result = await checker.check(finding, scope=scope, out_of_scope=[])
    assert result["in_scope"] is True
    assert result["is_known_false_positive"] is False


@pytest.mark.asyncio
async def test_context_checker_rejects_out_of_scope():
    checker = ContextChecker()
    finding = make_finding()
    result = await checker.check(finding, scope=["other.com"], out_of_scope=[])
    assert result["in_scope"] is False


@pytest.mark.asyncio
async def test_severity_assessor_returns_cvss():
    assessor = SeverityAssessor()
    finding = make_finding()
    semantic_model = {"app_type": "saas", "user_roles": ["user", "admin"]}
    mock_response = MagicMock()
    mock_response.content = '{"severity": "high", "cvss_score": 7.5, "business_impact": "Cross-user data exposure", "justification": "IDOR allows horizontal privilege escalation"}'
    with patch.object(assessor._llm, "ainvoke", return_value=mock_response):
        result = await assessor.assess(finding, semantic_model)
    assert result["severity"] == "high"
    assert result["cvss_score"] == 7.5


def test_scorer_passes_high_confidence():
    scorer = ConfidenceScorer(threshold=0.75)
    result = scorer.score(
        challenger_result={"reproduced": True, "confidence": 0.88},
        context_result={"in_scope": True, "is_known_false_positive": False},
        severity_result={"severity": "high", "cvss_score": 7.5},
    )
    assert result["final_score"] >= 0.75
    assert result["passes_gate"] is True


def test_scorer_fails_low_confidence():
    scorer = ConfidenceScorer(threshold=0.75)
    result = scorer.score(
        challenger_result={"reproduced": False, "confidence": 0.3},
        context_result={"in_scope": True, "is_known_false_positive": False},
        severity_result={"severity": "low", "cvss_score": 2.0},
    )
    assert result["passes_gate"] is False
```

- [ ] **Step 2: Run — verify they fail**

```bash
cd backend && pytest tests/test_validator.py -v
# Expected: ImportError
```

- [ ] **Step 3: Implement challenger.py**

```python
# backend/app/validator/challenger.py
import json
import re
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a skeptical security researcher verifying whether a reported finding is real.
Given a finding report, evaluate: is this reproducible? Is the evidence convincing?

Return ONLY valid JSON:
- reproduced: bool (would you be able to reproduce this with the given steps?)
- confidence: float (0.0–1.0 — how confident are you this is a real vulnerability?)
- notes: string (your assessment)
"""


class Challenger:
    def __init__(self):
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=500,
        )

    async def challenge(self, finding: dict) -> dict:
        user_content = f"""
Finding: {finding.get('title')}
Class: {finding.get('vulnerability_class')}
Surface: {finding.get('affected_surface')}
Description: {finding.get('description')}
Reproduction Steps: {json.dumps(finding.get('reproduction_steps', []))}
Evidence: {json.dumps(finding.get('evidence', []))}
"""
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
```

- [ ] **Step 4: Implement context.py**

```python
# backend/app/validator/context.py
from urllib.parse import urlparse

# Known false positive patterns by vulnerability class
FALSE_POSITIVE_PATTERNS = {
    "xss": ["alert(1) in non-reflected context", "CSP blocks execution"],
    "sqli": ["input sanitized before query", "ORM parameterized"],
}


class ContextChecker:
    async def check(self, finding: dict, scope: list[str], out_of_scope: list[str]) -> dict:
        surface = finding.get("affected_surface", "")
        vuln_class = finding.get("vulnerability_class", "")

        # Scope check
        in_scope = False
        if scope:
            try:
                parsed = urlparse(surface if surface.startswith("http") else f"https://{surface}")
                hostname = parsed.hostname or ""
                in_scope = any(
                    hostname == s or hostname.endswith(f".{s}") for s in scope
                )
            except Exception:
                in_scope = False
        else:
            in_scope = True  # no scope defined = everything in scope

        # Out of scope check
        for oos in out_of_scope:
            if oos in surface:
                in_scope = False
                break

        # False positive pattern check
        is_known_false_positive = False
        description = finding.get("description", "").lower()
        for pattern in FALSE_POSITIVE_PATTERNS.get(vuln_class, []):
            if pattern.lower() in description:
                is_known_false_positive = True
                break

        return {
            "in_scope": in_scope,
            "is_known_false_positive": is_known_false_positive,
            "surface": surface,
        }
```

- [ ] **Step 5: Implement severity.py**

```python
# backend/app/validator/severity.py
import json
import re
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from app.config import settings


SYSTEM_PROMPT = """You are a security expert assessing the severity of a vulnerability.
Given the finding and the application's semantic model, assess business impact.

Return ONLY valid JSON:
- severity: string (critical, high, medium, low, info)
- cvss_score: float (0.0–10.0)
- business_impact: string (one sentence)
- justification: string (why this severity)
"""


class SeverityAssessor:
    def __init__(self):
        self._llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=500,
        )

    async def assess(self, finding: dict, semantic_model: dict) -> dict:
        user_content = f"""
Finding: {finding.get('title')}
Class: {finding.get('vulnerability_class')}
Surface: {finding.get('affected_surface')}
Description: {finding.get('description')}
App Type: {semantic_model.get('app_type', 'unknown')}
User Roles: {semantic_model.get('user_roles', [])}
Business Flows: {semantic_model.get('business_flows', [])}
"""
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]
        response = await self._llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
```

- [ ] **Step 6: Implement scorer.py**

```python
# backend/app/validator/scorer.py
from dataclasses import dataclass
from app.config import settings


@dataclass
class ConfidenceScorer:
    threshold: float = None

    def __post_init__(self):
        if self.threshold is None:
            self.threshold = settings.confidence_threshold

    def score(
        self,
        challenger_result: dict,
        context_result: dict,
        severity_result: dict,
    ) -> dict:
        """Combine challenger, context, and severity into a final confidence score."""
        # Immediate disqualifiers
        if not context_result.get("in_scope", True):
            return {"final_score": 0.0, "passes_gate": False, "reason": "out_of_scope"}
        if context_result.get("is_known_false_positive", False):
            return {"final_score": 0.0, "passes_gate": False, "reason": "known_false_positive"}
        if not challenger_result.get("reproduced", False):
            return {"final_score": challenger_result.get("confidence", 0.0) * 0.3, "passes_gate": False, "reason": "not_reproduced"}

        # Weighted score
        challenger_score = challenger_result.get("confidence", 0.0)
        severity_boost = {
            "critical": 0.1, "high": 0.05, "medium": 0.0, "low": -0.05, "info": -0.1
        }.get(severity_result.get("severity", "medium"), 0.0)

        final_score = min(1.0, challenger_score + severity_boost)
        passes_gate = final_score >= self.threshold

        return {
            "final_score": round(final_score, 3),
            "passes_gate": passes_gate,
            "reason": "passed" if passes_gate else f"score_{final_score:.2f}_below_threshold_{self.threshold}",
            "severity": severity_result.get("severity"),
            "cvss_score": severity_result.get("cvss_score"),
            "business_impact": severity_result.get("business_impact"),
        }
```

- [ ] **Step 7: Run all validator tests — verify they pass**

```bash
cd backend && pytest tests/test_validator.py -v
# Expected: 5 PASSED
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/validator/
git commit -m "feat: full adversarial validator pipeline (Challenger, Context, Severity, Scorer)"
```

---

## Plan 3 Complete

At this point you have:
- All 6 agent types with bid scoring and execution
- Swarm Scheduler with bid auctions and lineage tracking
- Thread Health Monitor with automatic dead-thread termination
- Full 4-stage Adversarial Validator pipeline

**Next:** Plan 4 — API, WebSocket & Frontend
