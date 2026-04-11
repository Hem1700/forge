# backend/app/swarm/agents/fuzzer.py
from __future__ import annotations
import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from app.swarm.agents.base import BaseAgent

# Fuzz payloads by surface type
PAYLOADS: dict[str, list] = {
    'path_traversal': ['../../../etc/passwd', '..\\..\\..\\windows\\win.ini', '/dev/null', 'A' * 4096],
    'cli_arg': ['', ' ', '\x00', "'; ls #", '$(id)', '`id`', '-' * 200, '\n\n', '{}', '[]', 'null'],
    'env_var': ['', '\x00', '../../../etc/passwd', 'A' * 1024],
    'file_input': [b'', b'\x00' * 100, b'PK\x03\x04', b'\xff\xfe', b'A' * 10240, b'%!PS', b'\x7fELF'],
    'config': ['{}', '[]', 'null', '{invalid', "key: !!python/object:os.system ['id']"],
}


@dataclass
class FuzzerAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        target_path = task.get('target_path', '')
        semantic_model = task.get('semantic_model', {})
        attack_surfaces = semantic_model.get('attack_surfaces', [])

        findings: list[dict] = []
        tests_run = 0

        for surface in attack_surfaces[:8]:  # cap surfaces tested
            surface_type = surface.get('type', '')
            surface_name = surface.get('name', '')
            payloads = PAYLOADS.get(surface_type, PAYLOADS['cli_arg'])

            for payload in payloads[:5]:  # cap payloads per surface
                tests_run += 1
                result = await self._fuzz(target_path, semantic_model, surface, payload)
                if result:
                    findings.append({
                        'file': surface_name,
                        'line_hint': surface_type,
                        'vulnerability': f'crash_on_{surface_type}',
                        'severity': 'high' if 'crash' in result.get('type', '') else 'medium',
                        'description': result.get('description', ''),
                        'evidence': repr(payload)[:200],
                        'recommendation': f"Validate and sanitize {surface_type} input before processing",
                    })

        self.signal_history.append(1.0 if findings else 0.4)
        return {
            'agent_type': self.agent_type,
            'agent_id': self.agent_id,
            'findings': findings,
            'tests_run': tests_run,
        }

    async def _fuzz(self, target_path: str, model: dict, surface: dict, payload) -> dict | None:
        """Run a single fuzz test. Returns finding dict if anomaly detected, else None."""
        surface_type = surface.get('type', '')
        entry_points = model.get('entry_points', [])
        if not entry_points:
            return None

        # For file_input surfaces, write payload to a temp file and pass as arg
        if surface_type == 'file_input' and isinstance(payload, bytes):
            return await self._fuzz_file_input(target_path, model, payload)

        # For cli_arg surfaces, try running the entry point with the payload
        if surface_type in ('cli_arg', 'path_traversal'):
            return await self._fuzz_cli(target_path, model, str(payload))

        return None

    async def _fuzz_file_input(self, target_path: str, model: dict, payload: bytes) -> dict | None:
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(payload)
            tmp = f.name
        try:
            return await self._run_and_detect(target_path, model, extra_args=[tmp])
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    async def _fuzz_cli(self, target_path: str, model: dict, arg: str) -> dict | None:
        return await self._run_and_detect(target_path, model, extra_args=[arg])

    async def _run_and_detect(self, target_path: str, model: dict, extra_args: list[str]) -> dict | None:
        """Run the target with extra_args, detect crashes/errors. Returns finding or None."""
        entry_points = model.get('entry_points', [])
        if not entry_points:
            return None

        python = sys.executable
        cmd: list[str] = []

        # Look for a runnable pattern
        for ep in entry_points[:3]:
            ep_lower = ep.lower()
            if 'python' in ep_lower or ep_lower.endswith('.py'):
                main_py = Path(target_path) / 'main.py'
                if main_py.exists():
                    cmd = [python, str(main_py)] + extra_args
                    break
            elif '.' not in ep:  # likely a module name
                cmd = [python, '-m', ep] + extra_args
                break

        if not cmd:
            # Generic: try running any .py entry point
            for py in Path(target_path).glob('*.py'):
                cmd = [python, str(py)] + extra_args
                break

        if not cmd:
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=target_path,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except asyncio.TimeoutError:
                proc.kill()
                return {
                    'type': 'hang',
                    'description': f"Process hung with input {extra_args!r} — possible infinite loop or deadlock on malformed input",
                }

            combined = (stdout + stderr).decode(errors='replace').lower()
            crash_signals = ['traceback', 'segfault', 'segmentation fault', 'killed', 'exception', 'error: ', 'panic:']
            if proc.returncode not in (0, 1, 2) or any(s in combined for s in crash_signals):
                return {
                    'type': 'crash',
                    'description': f"Process exited with code {proc.returncode} on input {extra_args!r}. Stderr: {stderr.decode(errors='replace')[:300]}",
                }
        except Exception:
            pass
        return None
