# backend/app/swarm/agents/config_auditor.py
"""Rule-based config auditor.

Scans infrastructure-as-code and config files for common misconfigurations:
Dockerfile, docker-compose, Kubernetes manifests, nginx, Django/Flask settings,
GitHub Actions workflows, Terraform/IAM policies. Complements the LLM code
analyzer with fast, deterministic checks on config-shaped files.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.swarm.agents.base import BaseAgent
from app.ws import progress as ws_progress


SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env', 'dist', 'build', '.tox'}


@dataclass
class ConfigAuditorAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        target_path = task.get('target_path', '')
        if not target_path:
            return {"agent_type": self.agent_type, "agent_id": self.agent_id, "findings": []}
        root = Path(target_path)

        findings: list[dict] = []
        files_audited = 0

        handlers: list[tuple[str, callable]] = [
            ("dockerfile",         self._audit_dockerfile),
            ("docker_compose",     self._audit_docker_compose),
            ("k8s_manifest",       self._audit_k8s),
            ("nginx",              self._audit_nginx),
            ("github_actions",     self._audit_github_actions),
            ("iam_policy",         self._audit_iam_policy),
            ("django_settings",    self._audit_django_settings),
        ]

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                rel = str(fpath.relative_to(root))
                try:
                    if fpath.stat().st_size > 512_000:
                        continue
                    text = fpath.read_text(errors='replace')
                except Exception:
                    continue

                matched = False
                for _name, handler in handlers:
                    if self._matches(handler, fpath, text):
                        matched = True
                        for hit in handler(rel, text):
                            findings.append(hit)
                if matched:
                    files_audited += 1
                    if files_audited % 10 == 0:
                        await ws_progress.progress(
                            self.engagement_id, "config_auditor.file",
                            f"audited {files_audited} config files, {len(findings)} issues so far",
                            audited=files_audited, issues=len(findings),
                        )

        self.signal_history.append(1.0 if findings else 0.4)
        await ws_progress.progress(
            self.engagement_id, "config_auditor.done",
            f"audited {files_audited} config files — {len(findings)} issues",
        )
        return {
            'agent_type': self.agent_type,
            'agent_id': self.agent_id,
            'findings': findings,
            'files_audited': files_audited,
        }

    # ── dispatch matchers ───────────────────────────────────────
    def _matches(self, handler, fpath: Path, text: str) -> bool:
        name = fpath.name.lower()
        if handler is self._audit_dockerfile:
            return name == "dockerfile" or name.endswith(".dockerfile")
        if handler is self._audit_docker_compose:
            return name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
        if handler is self._audit_k8s:
            if fpath.suffix.lower() not in {".yaml", ".yml"}:
                return False
            return bool(re.search(r"^apiVersion:\s*\S+", text, re.M)) and bool(re.search(r"^kind:\s*\S+", text, re.M))
        if handler is self._audit_nginx:
            return name in {"nginx.conf"} or (fpath.suffix.lower() == ".conf" and "server_name" in text)
        if handler is self._audit_github_actions:
            return ".github/workflows/" in str(fpath).replace("\\", "/") and fpath.suffix.lower() in {".yml", ".yaml"}
        if handler is self._audit_iam_policy:
            if fpath.suffix.lower() != ".json":
                return False
            return '"Effect"' in text and '"Action"' in text
        if handler is self._audit_django_settings:
            return name == "settings.py" or name.endswith("/settings.py")
        return False

    # ── individual auditors ─────────────────────────────────────
    def _audit_dockerfile(self, rel: str, text: str) -> list[dict]:
        hits: list[dict] = []
        lines = text.splitlines()
        has_user_directive = any(re.match(r"^\s*USER\s+(?!root\b)\S+", l, re.I) for l in lines)
        if not has_user_directive:
            hits.append(self._make(rel, "L1", "container_root_default",
                "Dockerfile never sets a non-root USER — the container runs as root by default.",
                "USER root", "high",
                "Add a USER directive that drops to an unprivileged user before CMD/ENTRYPOINT."))
        for i, line in enumerate(lines, 1):
            if re.search(r"^\s*USER\s+root\b", line, re.I):
                hits.append(self._make(rel, f"L{i}", "container_root_explicit",
                    "Dockerfile explicitly sets USER root.", line.strip(), "high",
                    "Drop privileges with `USER app` (or similar) after installing packages."))
            if re.search(r"\bcurl\s+.*\|\s*(sh|bash)\b", line):
                hits.append(self._make(rel, f"L{i}", "curl_pipe_shell",
                    "Running a remote script via curl|sh during build — supply-chain + integrity risk.",
                    line.strip(), "medium",
                    "Pin versions, verify checksums, or vendor the dependency."))
            if re.search(r"^\s*ADD\s+https?://", line, re.I):
                hits.append(self._make(rel, f"L{i}", "dockerfile_add_url",
                    "ADD with a remote URL — no integrity check and harder to audit than COPY + explicit download.",
                    line.strip(), "low",
                    "Prefer COPY for local files; for remote, RUN curl with checksum verification."))
            if re.search(r"\bchmod\s+(-R\s+)?0?777\b", line):
                hits.append(self._make(rel, f"L{i}", "chmod_777",
                    "chmod 777 grants world-writable permissions.", line.strip(), "medium",
                    "Use the least-privilege mode your app actually needs (typically 0644 / 0755)."))
        return hits

    def _audit_docker_compose(self, rel: str, text: str) -> list[dict]:
        hits: list[dict] = []
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"^\s*privileged\s*:\s*true\b", line):
                hits.append(self._make(rel, f"L{i}", "docker_privileged",
                    "Container runs with privileged: true — equivalent to host root.",
                    line.strip(), "critical",
                    "Remove privileged:true and use targeted capabilities (cap_add) instead."))
            if re.search(r"^\s*network_mode\s*:\s*[\"']?host[\"']?", line):
                hits.append(self._make(rel, f"L{i}", "docker_host_network",
                    "network_mode: host shares the host's network stack with the container.",
                    line.strip(), "high",
                    "Use a bridge/overlay network and expose only the ports you need."))
            if re.search(r"-\s*/?:/", line) or re.search(r"\"/?\s*:\s*/\"", line):
                # Heuristic: bind-mounting / into the container
                if re.search(r"-\s*/:\s*/", line) or re.search(r"-\s*/:", line):
                    hits.append(self._make(rel, f"L{i}", "docker_bindmount_root",
                        "Bind-mounting the host root into the container.",
                        line.strip(), "critical",
                        "Mount only the specific directory the service needs."))
            if re.search(r"-\s*/var/run/docker\.sock", line):
                hits.append(self._make(rel, f"L{i}", "docker_socket_mount",
                    "Mounting the docker socket into a container — grants effective root on the host.",
                    line.strip(), "critical",
                    "Avoid docker-in-docker patterns; if required, use a rootless or restricted proxy like docker-socket-proxy."))
        return hits

    def _audit_k8s(self, rel: str, text: str) -> list[dict]:
        hits: list[dict] = []
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if re.search(r"^\s*privileged\s*:\s*true\b", line):
                hits.append(self._make(rel, f"L{i}", "k8s_privileged",
                    "Pod/container runs with securityContext.privileged=true.",
                    line.strip(), "critical",
                    "Remove privileged:true; use narrowly-scoped capabilities + PodSecurity Admission."))
            if re.search(r"^\s*runAsUser\s*:\s*0\b", line):
                hits.append(self._make(rel, f"L{i}", "k8s_run_as_root",
                    "runAsUser: 0 — container runs as root UID.",
                    line.strip(), "high",
                    "Set runAsUser to a non-zero UID and runAsNonRoot: true."))
            if re.search(r"^\s*hostNetwork\s*:\s*true\b", line):
                hits.append(self._make(rel, f"L{i}", "k8s_host_network",
                    "hostNetwork: true exposes the host's network stack to the pod.",
                    line.strip(), "high",
                    "Use Services/Ingress instead of hostNetwork."))
            if re.search(r"^\s*allowPrivilegeEscalation\s*:\s*true\b", line):
                hits.append(self._make(rel, f"L{i}", "k8s_privilege_escalation",
                    "allowPrivilegeEscalation: true permits setuid/setgid elevation inside the container.",
                    line.strip(), "medium",
                    "Set allowPrivilegeEscalation: false."))
        if re.search(r"^\s*kind:\s*Pod\b", text, re.M) and "resources:" not in text:
            hits.append(self._make(rel, "L1", "k8s_no_resource_limits",
                "Pod manifest declares no resource limits — a single pod can exhaust the node.",
                "no resources: block", "low",
                "Add requests + limits for cpu and memory."))
        return hits

    def _audit_nginx(self, rel: str, text: str) -> list[dict]:
        hits: list[dict] = []
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"^\s*server_tokens\s+on\s*;", line):
                hits.append(self._make(rel, f"L{i}", "nginx_server_tokens",
                    "server_tokens on — nginx version leaks in error pages and headers.",
                    line.strip(), "low",
                    "Set `server_tokens off;` in the http block."))
            if re.search(r"ssl_protocols\s+.*\b(SSLv2|SSLv3|TLSv1|TLSv1\.1)\b", line, re.I):
                hits.append(self._make(rel, f"L{i}", "nginx_weak_tls",
                    "ssl_protocols includes a deprecated protocol (SSLv2/3 or TLS 1.0/1.1).",
                    line.strip(), "high",
                    "Restrict to TLSv1.2 and TLSv1.3 only."))
            if re.search(r"add_header\s+Access-Control-Allow-Origin\s+\*", line, re.I):
                hits.append(self._make(rel, f"L{i}", "nginx_cors_wildcard",
                    "CORS allows any origin — paired with credentials this is a data-exfil risk.",
                    line.strip(), "medium",
                    "List specific trusted origins, or omit the header for public endpoints."))
        return hits

    def _audit_github_actions(self, rel: str, text: str) -> list[dict]:
        hits: list[dict] = []
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\$\{\{\s*github\.event\.(issue|pull_request|comment|review)\..*\}\}", line):
                if "run:" in text.lower() or "run: " in line:
                    hits.append(self._make(rel, f"L{i}", "gha_script_injection",
                        "Untrusted PR/issue input interpolated into a run: block — script injection risk.",
                        line.strip(), "high",
                        "Pass the value via env: and reference $VAR inside the script, so shell parsing can't expand it."))
            if re.search(r"on:\s*pull_request_target\b", line):
                hits.append(self._make(rel, f"L{i}", "gha_pull_request_target",
                    "pull_request_target runs with repo-write permissions on forked-PR code — risky without strict checks.",
                    line.strip(), "high",
                    "Prefer pull_request, or gate on trusted labels/users and checkout the PR head with limited permissions."))
        return hits

    def _audit_iam_policy(self, rel: str, text: str) -> list[dict]:
        hits: list[dict] = []
        # Find each Statement block's Effect / Action / Resource
        for m in re.finditer(r'"Effect"\s*:\s*"Allow".*?(?="Effect"|\Z)', text, re.S):
            block = m.group(0)
            if re.search(r'"Action"\s*:\s*"\*"', block) and re.search(r'"Resource"\s*:\s*"\*"', block):
                hits.append(self._make(rel, "policy", "iam_allow_star_star",
                    'Statement allows Action "*" on Resource "*" — effectively full admin.',
                    '"Effect":"Allow","Action":"*","Resource":"*"', "critical",
                    "Scope Action and Resource to the minimum the principal actually needs."))
            elif re.search(r'"Action"\s*:\s*"\*"', block):
                hits.append(self._make(rel, "policy", "iam_allow_all_actions",
                    'Statement allows Action "*" on a specific resource — still overly permissive.',
                    '"Action":"*"', "high",
                    "List only the API actions the principal needs."))
        return hits

    def _audit_django_settings(self, rel: str, text: str) -> list[dict]:
        hits: list[dict] = []
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"^\s*DEBUG\s*=\s*True\b", line):
                hits.append(self._make(rel, f"L{i}", "django_debug_true",
                    "DEBUG=True in settings — stack traces and env leak to any visitor in prod.",
                    line.strip(), "high",
                    "Drive DEBUG from an env var and default to False. Never set True in a shipped config."))
            if re.search(r'ALLOWED_HOSTS\s*=\s*\[\s*[\'"]\*[\'"]\s*\]', line):
                hits.append(self._make(rel, f"L{i}", "django_allowed_hosts_wildcard",
                    'ALLOWED_HOSTS = ["*"] — accepts any Host header, enabling host-header attacks.',
                    line.strip(), "medium",
                    "List explicit hostnames your deployment should answer for."))
            if re.search(r"SECRET_KEY\s*=\s*['\"][A-Za-z0-9_\-]{20,}['\"]", line):
                hits.append(self._make(rel, f"L{i}", "django_secret_hardcoded",
                    "SECRET_KEY is hardcoded in settings.py — any git reader can forge sessions.",
                    "SECRET_KEY = '...' (literal)", "critical",
                    "Load SECRET_KEY from env; rotate the current value."))
        return hits

    # ── helpers ─────────────────────────────────────────────────
    def _make(self, file: str, line_hint: str, kind: str, desc: str, evidence: str, severity: str, recommendation: str) -> dict:
        return {
            'file': file,
            'line_hint': line_hint,
            'vulnerability': kind,
            'severity': severity,
            'description': desc,
            'evidence': evidence,
            'recommendation': recommendation,
        }
