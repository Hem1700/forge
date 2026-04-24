# backend/app/swarm/agents/secret_scanner.py
"""Regex-based secret scanner.

Walks the codebase and looks for leaked credentials: cloud keys, tokens,
private keys, DB connection strings, high-entropy strings next to
secret-like variable names. No LLM — fast and deterministic.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.swarm.agents.base import BaseAgent
from app.ws import progress as ws_progress


# (name, severity, pattern, what-it-is)
# Patterns ordered specific → generic so the first match wins.
SECRET_PATTERNS: list[tuple[str, str, re.Pattern, str]] = [
    ("aws_access_key",   "critical", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),                                    "AWS access key id"),
    ("github_pat",       "critical", re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"),                                       "GitHub personal access token"),
    ("github_oauth",     "critical", re.compile(r"\b(gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),                         "GitHub OAuth/refresh token"),
    ("gitlab_pat",       "critical", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),                                  "GitLab personal access token"),
    ("slack_token",      "high",     re.compile(r"\bxox[abpors]-[A-Za-z0-9\-]{10,}\b"),                             "Slack API token"),
    ("stripe_secret",    "critical", re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b"),                                   "Stripe live secret key"),
    ("google_api_key",   "high",     re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),                                     "Google API key"),
    ("anthropic_key",    "critical", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{40,}\b"),                                 "Anthropic API key"),
    ("openai_key",       "critical", re.compile(r"\bsk-[A-Za-z0-9]{48,}\b"),                                        "OpenAI API key"),
    ("twilio_sid",       "high",     re.compile(r"\bAC[0-9a-fA-F]{32}\b"),                                          "Twilio account SID"),
    ("sendgrid_key",     "high",     re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b"),                 "SendGrid API key"),
    ("private_key",      "critical", re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),           "Private key block"),
    ("pg_conn_string",   "high",     re.compile(r"postgres(?:ql)?://[^:\s]+:([^@\s]{4,})@"),                        "Postgres connection string with password"),
    ("mysql_conn_string","high",     re.compile(r"mysql://[^:\s]+:([^@\s]{4,})@"),                                  "MySQL connection string with password"),
    ("jwt_token",        "medium",   re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), "JWT token"),
]

# Lower-confidence generic patterns — only triggered when paired with a secret-like key.
ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b(api[_\-]?key|secret|password|passwd|token|auth|private[_\-]?key|access[_\-]?key)
    \s*[:=]\s*
    ["']([A-Za-z0-9+/=_\-]{12,})["']
    """,
)

SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'dist', 'build', '.tox', '.pytest_cache'}
SKIP_EXTS = {'.min.js', '.map', '.lock', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf', '.zip', '.tar', '.gz', '.woff', '.woff2', '.ttf'}
SCAN_EXTS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rb', '.java', '.php', '.rs', '.c', '.cpp',
    '.cs', '.sh', '.yaml', '.yml', '.toml', '.json', '.env', '.cfg', '.ini', '.conf',
    '.properties', '.pem', '.key', '.sql', '.tf', '.tfvars', '.dockerfile', '',
}
MAX_FILE_BYTES = 512_000  # 500 KB — skip bigger files to keep this fast
MAX_HITS_PER_FILE = 20

# Common test-fixture values that should never trigger
WHITELIST = {
    "AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLEKEY",  # AWS docs
    "ghp_0000000000000000000000000000000000000000",
    "your-api-key-here", "your_api_key_here", "changeme", "password",
}


@dataclass
class SecretScannerAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        target_path = task.get('target_path', '')
        if not target_path:
            return {"agent_type": self.agent_type, "agent_id": self.agent_id, "findings": []}
        root = Path(target_path)

        files_scanned = 0
        findings: list[dict] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()
                name_lower = fname.lower()
                if ext in SKIP_EXTS:
                    continue
                # Accept files by extension OR by dotfile name (.env, .htaccess, etc.)
                if ext not in SCAN_EXTS and not name_lower.startswith('.'):
                    continue
                try:
                    if fpath.stat().st_size > MAX_FILE_BYTES:
                        continue
                    text = fpath.read_text(errors='replace')
                except Exception:
                    continue

                rel = str(fpath.relative_to(root))
                files_scanned += 1
                if files_scanned % 50 == 0:
                    await ws_progress.progress(
                        self.engagement_id, "secret_scanner.scan",
                        f"scanned {files_scanned} files, {len(findings)} hits so far",
                        files_scanned=files_scanned, hits=len(findings),
                    )

                hits_in_file = 0
                for name, sev, pattern, label in SECRET_PATTERNS:
                    if hits_in_file >= MAX_HITS_PER_FILE:
                        break
                    for m in pattern.finditer(text):
                        if m.group(0) in WHITELIST:
                            continue
                        line = text.count('\n', 0, m.start()) + 1
                        findings.append({
                            'file': rel,
                            'line_hint': f"L{line}",
                            'vulnerability': 'hardcoded_secret',
                            'secret_type': name,
                            'severity': sev,
                            'description': f"{label} detected in source — secrets committed to the repo can be extracted by anyone with read access.",
                            'evidence': _redact(m.group(0)),
                            'recommendation': "Rotate the credential immediately, remove it from git history (git filter-repo or BFG), and load it from a secret manager / env var at runtime.",
                        })
                        hits_in_file += 1

                if hits_in_file < MAX_HITS_PER_FILE:
                    for m in ASSIGNMENT_RE.finditer(text):
                        value = m.group(2)
                        if value in WHITELIST or value.lower() in ('true', 'false', 'null', 'none'):
                            continue
                        line = text.count('\n', 0, m.start()) + 1
                        findings.append({
                            'file': rel,
                            'line_hint': f"L{line}",
                            'vulnerability': 'hardcoded_secret',
                            'secret_type': f"assigned_{m.group(1).lower()}",
                            'severity': 'medium',
                            'description': f"Possible hardcoded {m.group(1)} assignment in source. Value is long enough to be a real credential — verify before dismissing.",
                            'evidence': _redact(m.group(0)),
                            'recommendation': "If this is a real credential, rotate it and move to a secret manager. If it's a placeholder/test value, rename it to make that obvious (e.g. TEST_API_KEY_PLACEHOLDER).",
                        })
                        hits_in_file += 1
                        if hits_in_file >= MAX_HITS_PER_FILE:
                            break

        self.signal_history.append(1.0 if findings else 0.3)
        await ws_progress.progress(
            self.engagement_id, "secret_scanner.done",
            f"scanned {files_scanned} files — {len(findings)} potential secrets",
        )
        return {
            'agent_type': self.agent_type,
            'agent_id': self.agent_id,
            'findings': findings,
            'files_scanned': files_scanned,
        }


def _redact(value: str) -> str:
    """Return a partially-redacted version of a match for evidence display."""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]} (len={len(value)})"
