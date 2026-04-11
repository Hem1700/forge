# backend/app/swarm/agents/dependency_scanner.py
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
import httpx
from app.swarm.agents.base import BaseAgent

OSV_API = "https://api.osv.dev/v1/query"

ECOSYSTEMS = {
    'requirements.txt': 'PyPI',
    'requirements-dev.txt': 'PyPI',
    'package.json': 'npm',
    'go.mod': 'Go',
    'Cargo.toml': 'crates.io',
    'Gemfile': 'RubyGems',
}


@dataclass
class DependencyScannerAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        target_path = task.get('target_path', '')
        root = Path(target_path)
        findings: list[dict] = []
        packages_checked = 0

        for dep_file, ecosystem in ECOSYSTEMS.items():
            fpath = root / dep_file
            if not fpath.exists():
                continue
            packages = self._parse_deps(fpath, ecosystem)
            for pkg in packages[:30]:  # cap per file
                packages_checked += 1
                vulns = await self._check_osv(pkg['name'], pkg.get('version'), ecosystem)
                for v in vulns:
                    findings.append({
                        'file': dep_file,
                        'package': pkg['name'],
                        'version': pkg.get('version', 'unknown'),
                        'vulnerability': 'known_cve',
                        'severity': self._osv_severity(v),
                        'description': v.get('summary', 'Known vulnerability in dependency'),
                        'evidence': f"CVE/OSV ID: {v.get('id', 'unknown')}",
                        'recommendation': f"Upgrade {pkg['name']} — see {v.get('id', '')} for details",
                        'osv_id': v.get('id', ''),
                    })

        self.signal_history.append(1.0 if findings else 0.5)
        return {
            'agent_type': self.agent_type,
            'agent_id': self.agent_id,
            'findings': findings,
            'packages_checked': packages_checked,
        }

    def _parse_deps(self, fpath: Path, ecosystem: str) -> list[dict]:
        text = fpath.read_text(errors='replace')
        pkgs: list[dict] = []
        if ecosystem == 'PyPI':
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # e.g. requests==2.28.0 or requests>=2.0
                m = re.match(r'^([A-Za-z0-9_\-\.]+)\s*([><=!~^]+\s*[\d\.]+)?', line)
                if m:
                    ver_str = m.group(2) or ''
                    ver = re.search(r'[\d\.]+', ver_str)
                    pkgs.append({'name': m.group(1), 'version': ver.group(0) if ver else None})
        elif ecosystem == 'npm':
            try:
                data = json.loads(text)
                for section in ('dependencies', 'devDependencies'):
                    for name, ver in data.get(section, {}).items():
                        ver = ver.lstrip('^~>=')
                        pkgs.append({'name': name, 'version': ver})
            except json.JSONDecodeError:
                pass
        elif ecosystem == 'Go':
            for line in text.splitlines():
                m = re.match(r'^\s+([^\s]+)\s+(v[\d\.]+)', line)
                if m:
                    pkgs.append({'name': m.group(1), 'version': m.group(2).lstrip('v')})
        return pkgs

    async def _check_osv(self, name: str, version: str | None, ecosystem: str) -> list[dict]:
        payload: dict = {'package': {'name': name, 'ecosystem': ecosystem}}
        if version:
            payload['version'] = version
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(OSV_API, json=payload)
                if resp.status_code == 200:
                    return resp.json().get('vulns', [])
        except Exception:
            pass
        return []

    def _osv_severity(self, vuln: dict) -> str:
        for sev in vuln.get('severity', []):
            score_str = sev.get('score', '')
            try:
                score = float(score_str)
                if score >= 9.0:
                    return 'critical'
                if score >= 7.0:
                    return 'high'
                if score >= 4.0:
                    return 'medium'
                return 'low'
            except (ValueError, TypeError):
                pass
        return 'medium'
