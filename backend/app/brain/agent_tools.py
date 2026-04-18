# backend/app/brain/agent_tools.py
from __future__ import annotations
import re
from abc import ABC, abstractmethod

import httpx
from app.brain.exploit_executor import ExploitExecutor


class AgentTool(ABC):
    """Base class for tools available to ReAct agents."""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, args: dict) -> str:
        ...


class HttpRequestTool(AgentTool):
    """Make HTTP requests and return status, headers, and body."""

    name = "http_request"
    description = (
        "Make an HTTP request. "
        "Args: method (GET/POST/PUT/DELETE), url (string), "
        "headers (dict, optional), body (string, optional), params (dict, optional). "
        "Returns status code, response headers, and body (truncated to 4000 chars)."
    )

    async def execute(self, args: dict) -> str:
        method = args.get("method", "GET").upper()
        url = args.get("url", "")
        headers = args.get("headers") or {}
        body = args.get("body")
        params = args.get("params") or {}

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                    params=params,
                )
        except httpx.RequestError as exc:
            return f"request error: {exc}"

        headers_str = "\n".join(f"{k}: {v}" for k, v in resp.headers.items())
        body_preview = resp.text[:4000]
        return f"STATUS {resp.status_code}\nHEADERS\n{headers_str}\nBODY\n{body_preview}"


class ExtractPatternTool(AgentTool):
    """Extract patterns from text using regex or xpath."""

    name = "extract_pattern"
    description = (
        "Extract patterns from text. "
        "Args: pattern (regex string), text (string to search), "
        "mode ('regex' or 'xpath', default 'regex'). "
        "Returns comma-separated matches or 'no matches found'."
    )

    async def execute(self, args: dict) -> str:
        pattern = args.get("pattern", "")
        text = args.get("text", "")
        mode = args.get("mode", "regex")

        if mode == "xpath":
            try:
                from lxml import etree  # type: ignore[import]
                tree = etree.fromstring(text.encode())
                results = [str(m) for m in tree.xpath(pattern)]
            except ImportError:
                return "xpath not available — use mode: regex"
            except Exception as exc:
                return f"xpath error: {exc}"
        else:
            try:
                results = re.findall(pattern, text)
            except re.error as exc:
                return f"regex error: {exc}"

        if not results:
            return "no matches found"
        return ", ".join(str(r) for r in results[:50])


class SubprocessTool(AgentTool):
    """Run security tools inside an isolated Kali Linux Docker container."""

    name = "subprocess_tool"
    description = (
        "Run a security tool inside a Docker container (kalilinux/kali-rolling). "
        "Args: tool (one of: sqlmap, ffuf, curl, nikto), args (command-line arguments string). "
        "Returns exit code and output (truncated to 4000 chars). Timeout: 120s."
    )

    ALLOWED_TOOLS = {"sqlmap", "ffuf", "curl", "nikto"}

    async def execute(self, args: dict) -> str:
        tool_name = args.get("tool", "")
        tool_args = args.get("args", "")

        if tool_name not in self.ALLOWED_TOOLS:
            return (
                f"Error: '{tool_name}' is not an allowed tool. "
                f"Choose from: {', '.join(sorted(self.ALLOWED_TOOLS))}"
            )

        # Note: tool_args is passed to the container shell as-is. Only use with trusted input.
        script = f"#!/bin/bash\n{tool_name} {tool_args}"
        executor = ExploitExecutor()
        result = await executor.execute(
            script=script,
            language="bash",
            setup=[],
            timeout=120,
            image="kalilinux/kali-rolling",
        )
        output = (result["stdout"] or result["stderr"] or "")[:4000]
        return f"EXIT {result['exit_code']}\nOUTPUT\n{output}"
