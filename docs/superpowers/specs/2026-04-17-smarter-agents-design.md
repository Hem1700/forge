# FORGE Plan 12 — Smarter Agents (ReAct-Driven Execution)

**Date:** 2026-04-17  
**Status:** Approved  
**Scope:** Full ReAct reasoning loop for all execution agents, confidence-threshold termination, HTTP + Docker subprocess tools

---

## Overview

Plan 12 upgrades all FORGE execution agents (`ReconAgent`, `ProbeAgent`, `DeepExploitAgent`) from deterministic hardcoded-payload executors to LLM-driven autonomous reasoners. Each agent gains a `AgentBrain` that runs a ReAct (Reason + Act) loop: the LLM observes context, picks a tool, executes it, interprets the result, updates its confidence, and repeats until it reaches a confidence threshold (≥ 0.85) or exhausts its step budget (20 steps max).

The existing agent lifecycle — bidding, signals, dead-agent detection, `SwarmScheduler` auction — is untouched. Only `_execute()` changes in each agent.

---

## 1. Architecture

```
CampaignPlanner → hypothesis list
    ↓
SwarmScheduler → assigns to agents via auction
    ↓
Agent._execute()
    └→ AgentBrain.run(hypothesis, context, tools)
           ↓
        ReAct loop:
          1. LLM reasons: "what do I do next?"
          2. LLM picks a tool + args
          3. Tool executes (HTTP or Docker subprocess)
          4. Result fed back to LLM
          5. LLM updates confidence
          6. confidence ≥ 0.85 → stop, return findings
    ↓
Finding emitted via existing emit_signal()
```

**Three tool categories:**
- `HttpRequestTool` — crafts and fires HTTP requests (method, URL, headers, body, params) via `httpx.AsyncClient`
- `ExtractPatternTool` — regex/xpath extraction on response bodies, returns matches
- `SubprocessTool` — runs `sqlmap`, `ffuf`, `curl`, `nikto` inside a `kalilinux/kali-rolling` Docker container, reusing the `ExploitExecutor` pattern from Plan 11

---

## 2. `AgentBrain` (new brain component)

**File:** `backend/app/brain/agent_brain.py`

### Interface

```python
@dataclass
class AgentBrainResult:
    findings: list[dict]
    confidence: float
    steps_taken: int
    reasoning_trace: list[dict]  # ephemeral, not persisted

class AgentBrain:
    def __init__(
        self,
        system_prompt: str,
        tools: list[AgentTool],
        confidence_threshold: float = 0.85,
        max_steps: int = 20,
    ): ...

    async def run(self, hypothesis: dict, context: dict) -> AgentBrainResult: ...
```

### ReAct loop

Each iteration, the LLM receives the full conversation history (hypothesis + all prior tool calls + results) and outputs one of:

**Tool call:**
```json
{
  "tool": "http_request",
  "args": {"method": "GET", "url": "https://target.com/api/users?id=1'"},
  "reasoning": "Testing for SQL injection via id parameter",
  "confidence": 0.4
}
```

**Conclusion:**
```json
{
  "conclusion": true,
  "confidence": 0.91,
  "findings": [{"vulnerability_class": "sqli", "evidence": "...", "severity": "critical"}],
  "reasoning": "Error-based SQLi confirmed via MySQL syntax error in response"
}
```

Loop terminates when `confidence ≥ confidence_threshold` OR `steps == max_steps`.

### Design decisions
- **Same `_LLMWrapper` pattern** as all other brain components — `ainvoke` is a plain instance attribute, patchable in tests without `mock.patch()`
- **Full history passed each iteration** — LLM sees all prior tool calls and results; no summarization
- **max_steps = 20** as a safety ceiling to prevent runaway loops on unresponsive targets
- **Model:** `claude-sonnet-4-6`

---

## 3. `AgentTool` interface

**File:** `backend/app/brain/agent_tools.py`

```python
class AgentTool:
    name: str
    description: str

    async def execute(self, args: dict) -> str: ...
```

### `HttpRequestTool`
- Uses `httpx.AsyncClient` with 30s timeout
- Returns formatted string: `STATUS {code}\nHEADERS\n{headers}\nBODY\n{body[:4000]}`
- Truncates body to 4000 chars to stay within context limits

### `ExtractPatternTool`
- Args: `{"pattern": "...", "text": "...", "mode": "regex"|"xpath"}`
- Returns comma-separated matches or "no matches found"

### `SubprocessTool`
- Args: `{"tool": "sqlmap"|"ffuf"|"curl"|"nikto", "args": "..."}`
- Dispatches to `ExploitExecutor` with `kalilinux/kali-rolling` image
- Returns stdout (truncated to 4000 chars) + exit code
- 120s timeout (longer than exploit execution — tool scans take time)

---

## 4. Agent Integration

Each agent composes in `AgentBrain` with its own system prompt and tool set. `_execute()` becomes a thin delegation.

**File changes:**
- `backend/app/swarm/agents/recon.py` — modify `_execute()`
- `backend/app/swarm/agents/probe.py` — modify `_execute()`
- `backend/app/swarm/agents/deep_exploit.py` — modify `_execute()`

### Per-agent system prompts

**ReconAgent:**
> You are a recon specialist. Your goal is to map the attack surface: discover endpoints, identify technologies and frameworks, enumerate parameters, surface authentication boundaries. Do NOT exploit — your job is to produce a comprehensive target map for probe agents. Report everything unusual.

**ProbeAgent:**
> You are a vulnerability prober. You receive a specific attack hypothesis. Test it with targeted payloads, vary your approach based on responses, and determine with high confidence whether the vulnerability exists. Report confirmed findings with evidence.

**DeepExploitAgent:**
> You are an exploitation specialist. A vulnerability has already been confirmed. Your job is to achieve maximum impact: extract data, execute commands, bypass authentication, enumerate the system. Use every tool available. Report what you achieved with evidence.

### Integration pattern

```python
class ProbeAgent(BaseAgent):
    def __init__(self, ...):
        super().__init__(...)
        self.brain = AgentBrain(
            system_prompt=PROBE_SYSTEM_PROMPT,
            tools=[HttpRequestTool(), ExtractPatternTool(), SubprocessTool()],
            confidence_threshold=0.85,
        )

    async def _execute(self, task: dict) -> dict:
        result = await self.brain.run(task["hypothesis"], task["context"])
        return {"findings": result.findings, "confidence": result.confidence}
```

**What does NOT change:**
- `BaseAgent` — bidding, signals, lifecycle, `is_dead()` all untouched
- `SwarmScheduler` — auction assignment untouched
- `CampaignPlanner` — hypothesis list generation untouched
- `emit_signal()` — findings still flow via existing signal system

---

## 5. Data Model

No new database columns. `AgentBrainResult` is an in-memory dataclass. Findings flow through the existing `emit_signal()` path and are persisted via the existing `Finding` model. Reasoning traces are ephemeral (not stored).

---

## 6. Testing

**Brain unit tests (mocked LLM, no Docker):**
- `backend/tests/test_agent_brain.py` — mock `_LLMWrapper.ainvoke` to return scripted tool calls + conclusion; assert loop terminates at confidence threshold; assert max_steps ceiling fires correctly
- `backend/tests/test_agent_tools.py` — mock `httpx.AsyncClient` for `HttpRequestTool`; mock `ExploitExecutor` for `SubprocessTool`; assert correct request construction and truncation

**Agent unit tests (mocked brain):**
- `backend/tests/test_recon_agent.py` — mock `AgentBrain.run`, assert `_execute()` returns correct structure
- `backend/tests/test_probe_agent.py` — same pattern
- `backend/tests/test_deep_exploit_agent.py` — same pattern

---

## 7. File Checklist

| File | Change |
|------|--------|
| `backend/app/brain/agent_brain.py` | New — `AgentBrain`, `AgentBrainResult`, `_LLMWrapper` |
| `backend/app/brain/agent_tools.py` | New — `AgentTool`, `HttpRequestTool`, `ExtractPatternTool`, `SubprocessTool` |
| `backend/app/swarm/agents/recon.py` | Modify `_execute()` to delegate to `AgentBrain` |
| `backend/app/swarm/agents/probe.py` | Modify `_execute()` to delegate to `AgentBrain` |
| `backend/app/swarm/agents/deep_exploit.py` | Modify `_execute()` to delegate to `AgentBrain` |
| `backend/requirements.txt` | Add `httpx` if not present |
| `backend/tests/test_agent_brain.py` | New — unit tests (mocked LLM) |
| `backend/tests/test_agent_tools.py` | New — unit tests (mocked HTTP + Docker) |
| `backend/tests/test_recon_agent.py` | New/extend — unit tests (mocked brain) |
| `backend/tests/test_probe_agent.py` | New/extend — unit tests (mocked brain) |
| `backend/tests/test_deep_exploit_agent.py` | New/extend — unit tests (mocked brain) |

---

## 8. Out of Scope (Plan 12)

- Chained agent reasoning (one agent passes context to the next in sequence)
- Persistent reasoning traces / audit log in the database
- UI/CLI for viewing reasoning traces
- Agent self-improvement or learning across engagements
- `FuzzerAgent` (file/CLI fuzzing — different domain, not HTTP-based)
- New agent types
