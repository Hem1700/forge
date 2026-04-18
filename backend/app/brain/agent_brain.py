# backend/app/brain/agent_brain.py
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.brain.agent_tools import AgentTool


class _LLMWrapper:
    """Thin wrapper so ainvoke is a plain instance attribute — patchable in tests."""

    def __init__(self, llm):
        self._llm = llm

    async def ainvoke(self, messages):
        return await self._llm.ainvoke(messages)


@dataclass
class AgentBrainResult:
    findings: list[dict]
    confidence: float
    steps_taken: int
    reasoning_trace: list[dict] = field(default_factory=list)


class AgentBrain:
    """ReAct-style reasoning loop for LLM-driven agent execution.

    Runs observe → reason → act cycles. Each cycle the LLM either
    picks a tool to execute or emits a conclusion. Loop ends when
    confidence ≥ threshold or step budget is exhausted.
    """

    def __init__(
        self,
        system_prompt: str,
        tools: list[AgentTool],
        confidence_threshold: float = 0.85,
        max_steps: int = 20,
    ):
        _chat = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=4000,
        )
        self._llm = _LLMWrapper(_chat)
        self.system_prompt = system_prompt
        self.tools: dict[str, AgentTool] = {t.name: t for t in tools}
        self.confidence_threshold = confidence_threshold
        self.max_steps = max_steps

    def _build_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            f"- {name}: {tool.description}"
            for name, tool in self.tools.items()
        )
        return (
            f"{self.system_prompt}\n\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            "At each step, respond with ONLY valid JSON in one of these two formats:\n\n"
            "Tool call:\n"
            '{"tool": "<tool_name>", "args": {<tool-specific args>}, '
            '"reasoning": "<why this action>", "confidence": <0.0-1.0>}\n\n'
            "Conclusion (when done or confidence is high):\n"
            '{"conclusion": true, "confidence": <0.0-1.0>, '
            '"findings": [{"vulnerability_class": "<class>", "severity": "<critical|high|medium|low>", '
            '"evidence": "<observed evidence>", "description": "<details>"}], '
            '"reasoning": "<summary of what you found>"}\n\n'
            "Stop when your confidence is high or you have exhausted reasonable approaches."
        )

    async def run(self, hypothesis: dict, context: dict) -> AgentBrainResult:
        """Run the ReAct loop for a given hypothesis and target context."""
        messages = [
            SystemMessage(content=self._build_system_prompt()),
            HumanMessage(
                content=(
                    f"Hypothesis: {json.dumps(hypothesis)}\n"
                    f"Context: {json.dumps(context)}\n\n"
                    "Begin."
                )
            ),
        ]
        trace: list[dict] = []
        steps = 0

        while steps < self.max_steps:
            response = await self._llm.ainvoke(messages)
            text = response.content.strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                steps += 1
                break

            trace.append(parsed)
            steps += 1

            if parsed.get("conclusion"):
                return AgentBrainResult(
                    findings=parsed.get("findings", []),
                    confidence=float(parsed.get("confidence", 0.0)),
                    steps_taken=steps,
                    reasoning_trace=trace,
                )

            tool_name = parsed.get("tool", "")
            tool_args = parsed.get("args", {})
            confidence = float(parsed.get("confidence", 0.0))

            if confidence >= self.confidence_threshold:
                return AgentBrainResult(
                    findings=[],
                    confidence=confidence,
                    steps_taken=steps,
                    reasoning_trace=trace,
                )

            tool = self.tools.get(tool_name)
            if tool is None:
                tool_result = (
                    f"Error: unknown tool '{tool_name}'. "
                    f"Available tools: {list(self.tools)}"
                )
            else:
                try:
                    tool_result = await tool.execute(tool_args)
                except Exception as exc:
                    tool_result = f"Tool error: {exc}"

            messages.append(response)
            messages.append(HumanMessage(content=f"Tool result:\n{tool_result}"))

        return AgentBrainResult(
            findings=[],
            confidence=0.0,
            steps_taken=steps,
            reasoning_trace=trace,
        )
