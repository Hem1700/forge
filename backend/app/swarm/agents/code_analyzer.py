# backend/app/swarm/agents/code_analyzer.py
from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from app.swarm.agents.base import BaseAgent
from app.config import settings

SYSTEM_PROMPT = """You are a senior application security engineer performing a code security review.
Analyze the provided source code for security vulnerabilities.

Return ONLY a valid JSON array. Each item must have:
- file: string (relative file path)
- line_hint: string (line number or function name where issue appears, e.g. "L42" or "parse_input()")
- vulnerability: string (vuln type: sqli, cmdi, path_traversal, hardcoded_secret, insecure_deserialization, ssrf, xxe, open_redirect, weak_crypto, missing_auth, idor, prototype_pollution, prompt_injection, sandbox_escape, other)
- severity: string (critical, high, medium, low)
- description: string (what the vulnerability is and why it's exploitable)
- evidence: string (the actual vulnerable code snippet)
- recommendation: string (how to fix it)

Return [] if no vulnerabilities found. Maximum 20 findings.
"""

SOURCE_EXTENSIONS = {'.py', '.js', '.ts', '.go', '.rb', '.java', '.php', '.rs', '.c', '.cpp', '.cs', '.sh'}
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build'}
MAX_FILE_CHARS = 4000


@dataclass
class CodeAnalyzerAgent(BaseAgent):
    _llm: object = field(default=None, init=False, repr=False)

    def __post_init__(self):
        _chat = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=4000,
        )
        from app.brain.codebase_modeler import _LLMWrapper
        self._llm = _LLMWrapper(_chat)

    async def _execute(self, task: dict) -> dict:
        target_path = task.get('target_path', '')
        semantic_model = task.get('semantic_model', {})
        interesting_files = semantic_model.get('interesting_files', [])

        root = Path(target_path)

        # Prioritize interesting_files from semantic model, then walk the rest
        files_to_review: list[dict] = []
        seen: set[str] = set()

        for rel in interesting_files:
            fpath = root / rel
            if fpath.exists() and fpath.suffix.lower() in SOURCE_EXTENSIONS:
                try:
                    content = fpath.read_text(errors='replace')[:MAX_FILE_CHARS]
                    files_to_review.append({'path': rel, 'content': content})
                    seen.add(str(fpath))
                except Exception:
                    pass

        # Fill up to 15 files from walk
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if str(fpath) in seen or len(files_to_review) >= 15:
                    continue
                if fpath.suffix.lower() in SOURCE_EXTENSIONS:
                    try:
                        content = fpath.read_text(errors='replace')[:MAX_FILE_CHARS]
                        rel = str(fpath.relative_to(root))
                        files_to_review.append({'path': rel, 'content': content})
                        seen.add(str(fpath))
                    except Exception:
                        pass

        all_findings: list[dict] = []
        # Review in batches of 5 files
        for i in range(0, len(files_to_review), 5):
            batch = files_to_review[i:i + 5]
            code_block = "\n\n".join(
                f"### {f['path']}\n```\n{f['content']}\n```" for f in batch
            )
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"App type: {semantic_model.get('app_type', 'unknown')}\n\nSource files:\n{code_block}"),
            ]
            try:
                response = await self._llm.ainvoke(messages)
                text = response.content.strip()
                text = re.sub(r'^```json\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
                batch_findings = json.loads(text)
                if isinstance(batch_findings, list):
                    all_findings.extend(batch_findings)
            except Exception:
                pass

        self.signal_history.append(1.0 if all_findings else 0.3)
        return {
            'agent_type': self.agent_type,
            'agent_id': self.agent_id,
            'findings': all_findings,
            'files_reviewed': len(files_to_review),
        }
