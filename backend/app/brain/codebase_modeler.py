# backend/app/brain/codebase_modeler.py
from __future__ import annotations
import os
import json
import re
from pathlib import Path
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from app.config import settings
from app.ws import progress as ws_progress

SYSTEM_PROMPT = """You are a senior security engineer analyzing a local codebase for a security assessment.
Given a summary of the codebase structure and source code samples, produce a structured security model.

Return ONLY valid JSON with these fields:
- app_type: string (cli-tool, web-api, library, desktop-app, microservice, other)
- languages: list of strings (detected programming languages)
- frameworks: list of strings (detected frameworks and libraries)
- entry_points: list of strings (main entry points: CLI commands, main functions, API routes)
- attack_surfaces: list of objects with {name, type, description, risk_level} where type is one of: file_input, cli_arg, env_var, config_file, network, subprocess, database, deserialization, template
- data_flows: list of strings (how data moves through the app: user input → processing → storage)
- trust_boundaries: list of strings (where untrusted input enters the system)
- dependencies: list of strings (key third-party dependencies)
- interesting_files: list of strings (file paths most relevant for security review)
"""


class _LLMWrapper:
    def __init__(self, llm):
        self._llm = llm

    async def ainvoke(self, messages):
        return await self._llm.ainvoke(messages)


class CodebaseModeler:
    # Extensions to read as source code
    SOURCE_EXTENSIONS = {
        '.py', '.js', '.ts', '.go', '.rb', '.java', '.php', '.rs', '.c',
        '.cpp', '.h', '.cs', '.sh', '.yaml', '.yml', '.toml', '.json',
        '.env', '.cfg', '.ini', '.conf',
    }
    # Files to always include if present
    PRIORITY_FILES = {
        'requirements.txt', 'package.json', 'go.mod', 'Cargo.toml', 'Gemfile',
        'pom.xml', 'setup.py', 'pyproject.toml', 'Dockerfile',
        'docker-compose.yml', '.env.example', 'README.md', 'Makefile',
    }
    # Dirs to skip
    SKIP_DIRS = {
        '.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
        'dist', 'build', '.pytest_cache', '.mypy_cache', 'coverage', '.tox',
    }
    MAX_FILE_CHARS = 3000
    MAX_FILES = 40

    def __init__(self):
        _chat = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            max_tokens=3000,
        )
        self._llm = _LLMWrapper(_chat)

    def profile(self, target_path: str) -> dict:
        """Walk the directory and collect file metadata + content samples."""
        root = Path(target_path)
        files_collected: list[dict] = []
        structure: list[str] = []

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skip dirs in-place
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            rel_dir = Path(dirpath).relative_to(root)
            for fname in filenames:
                rel_path = str(rel_dir / fname)
                structure.append(rel_path)
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()
                is_priority = fname in self.PRIORITY_FILES
                if (ext in self.SOURCE_EXTENSIONS or is_priority) and len(files_collected) < self.MAX_FILES:
                    try:
                        content = fpath.read_text(errors='replace')[:self.MAX_FILE_CHARS]
                        files_collected.append({'path': rel_path, 'content': content, 'priority': is_priority})
                    except Exception:
                        pass

        return {
            'root': target_path,
            'structure': structure[:200],
            'files': files_collected,
        }

    async def build(self, target_path: str, engagement_id: str | None = None) -> dict:
        """Build security model of a local codebase."""
        await ws_progress.progress(engagement_id, "codebase_modeling.walk", f"walking {target_path}")
        profile = self.profile(target_path)
        await ws_progress.progress(
            engagement_id, "codebase_modeling.walk",
            f"walked {len(profile['structure'])} files, {len(profile['files'])} selected for review",
            files_found=len(profile['structure']),
            files_selected=len(profile['files']),
        )

        # Build a compact summary for the LLM
        file_summary = "\n\n".join(
            f"### {f['path']}\n```\n{f['content'][:1500]}\n```"
            for f in sorted(profile['files'], key=lambda x: (not x['priority'], x['path']))[:20]
        )

        user_content = f"""Target path: {target_path}

Directory structure (first 100 entries):
{chr(10).join(profile['structure'][:100])}

Key file contents:
{file_summary}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        await ws_progress.progress(engagement_id, "codebase_modeling.llm", "sending codebase summary to LLM")
        response = await self._llm.ainvoke(messages)
        await ws_progress.progress(engagement_id, "codebase_modeling.llm", "LLM returned — parsing security model")
        text = response.content.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        result = json.loads(text)
        result['_profile'] = {'root': profile['root'], 'file_count': len(profile['files'])}
        return result
