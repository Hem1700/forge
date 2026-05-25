# backend/app/swarm/agents/privesc_agent.py
"""PrivescAgent — identifies privilege escalation paths on a Linux host.

Deterministic checks (GTFOBins, writable cron, docker group, NFS no_root_squash)
run without LLM. Sudo rule analysis uses LLM (HEAVY tier).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.brain.llm_factory import TaskType, get_llm
from app.brain.os_fingerprint import OSFingerprint
from app.swarm.agents.base import BaseAgent
from app.ws import progress as ws_progress

logger = logging.getLogger(__name__)

# Load GTFOBins once at import time
_GTFOBINS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "gtfobins.json"
_GTFOBINS: dict = {}
try:
    _GTFOBINS = json.loads(_GTFOBINS_PATH.read_text())
except Exception:
    logger.warning("PrivescAgent: could not load gtfobins.json from %s", _GTFOBINS_PATH)

_DANGEROUS_SUDO_BINARIES = {
    "vim", "vi", "nano", "find", "python", "python3", "perl", "ruby", "awk",
    "bash", "sh", "dash", "zsh", "cp", "mv", "tee", "dd", "tar", "zip",
    "git", "less", "more", "man", "env", "socat", "nc", "netcat", "node",
    "php", "lua", "gdb", "rsync", "wget", "curl", "chmod", "chown", "docker",
    "expect", "nmap", "strace",
}

_PRIVESC_SUDO_SYSTEM_PROMPT = (
    "You are a senior red-team operator. Analyze the following sudo rules and "
    "system context for exploitable privilege escalation paths. For each path: "
    "1) state the technique name, 2) provide the exact command sequence an attacker "
    "would run, 3) note whether user interaction is required, 4) cite GTFOBins if "
    "applicable. Return ONLY a JSON array. Each item: "
    '{"technique": str, "commands": [str], "requires_interaction": bool, "gtfobins_ref": str|null, '
    '"severity": "critical"|"high"|"medium", "description": str}. '
    "Return [] if no exploitable paths found."
)


@dataclass
class PrivescAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        fp_dict = task.get("fingerprint", {})
        fp = _dict_to_fp(fp_dict)

        findings: list[dict] = []
        org_id = task.get("org_id")

        # 1. GTFOBins SUID lookup (deterministic, no LLM)
        for binary_path in fp.suid_binaries:
            name = os.path.basename(binary_path)
            match = _GTFOBINS.get(name)
            if match and "suid" in match:
                findings.append({
                    "vulnerability": "suid_gtfobins",
                    "severity": "high",
                    "description": f"SUID binary {binary_path} has known GTFOBins SUID technique.",
                    "evidence": f"Path: {binary_path}\nCommands: {match['suid']['commands']}",
                    "recommendation": f"Remove SUID bit: chmod -s {binary_path}",
                    "chain_potential": True,
                    "confidence_score": 0.95,
                })

        await ws_progress.progress(
            self.engagement_id, "privesc.suid_done",
            f"SUID check: {len(fp.suid_binaries)} binaries, "
            f"{len([f for f in findings if f['vulnerability']=='suid_gtfobins'])} GTFOBins hits",
        )

        # 2. Writable cron paths (deterministic)
        cron_commands = []
        for job in fp.cron_jobs:
            sched = job.get("schedule", "")
            parts = sched.split()
            if len(parts) >= 6:
                cmd = " ".join(parts[5:])
                cron_commands.append(cmd)

        for wpath in fp.writable_paths:
            for cmd in cron_commands:
                if wpath in cmd:
                    findings.append({
                        "vulnerability": "writable_cron_path",
                        "severity": "high",
                        "description": (
                            f"Writable path {wpath} appears in a cron job command. "
                            "An attacker can modify scripts executed by cron."
                        ),
                        "evidence": f"Writable: {wpath}\nCron command: {cmd}",
                        "recommendation": (
                            f"Remove write permissions from {wpath} or restrict cron job ownership."
                        ),
                        "chain_potential": True,
                        "confidence_score": 0.90,
                    })
                    break

        # 3. Docker group (deterministic)
        current_users_in_docker = []
        for grp in fp.groups:
            if grp.get("name") == "docker":
                current_users_in_docker = grp.get("members", [])
                break
        if current_users_in_docker:
            findings.append({
                "vulnerability": "docker_group_privesc",
                "severity": "high",
                "description": (
                    f"Users in the docker group can escalate to root via "
                    f"'docker run -v /:/mnt'. Affected: {', '.join(current_users_in_docker)}"
                ),
                "evidence": f"docker group members: {current_users_in_docker}",
                "recommendation": (
                    "Remove non-admin users from the docker group. "
                    "Use rootless Docker or Podman."
                ),
                "chain_potential": True,
                "confidence_score": 0.85,
            })

        # 4. NFS no_root_squash (deterministic)
        for mount in fp.mounts:
            opts = mount.get("options", "")
            if mount.get("fstype") == "nfs" and "no_root_squash" in opts:
                findings.append({
                    "vulnerability": "nfs_no_root_squash",
                    "severity": "high",
                    "description": (
                        f"NFS mount {mount.get('mountpoint')} has no_root_squash — "
                        "a remote root user maps to local root."
                    ),
                    "evidence": f"Mount: {mount}",
                    "recommendation": "Add root_squash to NFS export options in /etc/exports.",
                    "chain_potential": False,
                    "confidence_score": 0.90,
                })

        # 5. Sudo rules analysis (LLM) — only run if there are interesting rules
        nopasswd_rules = [r for r in fp.sudo_rules if "NOPASSWD" in r.upper()]
        dangerous_sudo = [
            r for r in fp.sudo_rules
            if any(b in r.lower() for b in _DANGEROUS_SUDO_BINARIES)
        ]
        if nopasswd_rules or dangerous_sudo:
            try:
                llm = await get_llm(TaskType.privesc_analysis, org_id=org_id)
                context = {
                    "sudo_rules": fp.sudo_rules[:50],
                    "users": [u.get("username") for u in fp.users[:20]],
                    "groups": [g.get("name") for g in fp.groups[:20]],
                    "nopasswd_count": len(nopasswd_rules),
                }
                messages = [
                    SystemMessage(content=_PRIVESC_SUDO_SYSTEM_PROMPT),
                    HumanMessage(content=json.dumps(context)),
                ]
                resp = await llm.ainvoke(messages)
                raw = resp.content.strip()
                if raw.startswith("```"):
                    raw = raw.split("```", 2)[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.rsplit("```", 1)[0].strip()
                llm_paths = json.loads(raw)
                if isinstance(llm_paths, list):
                    for path in llm_paths:
                        findings.append({
                            "vulnerability": "sudo_privesc",
                            "severity": path.get("severity", "high"),
                            "description": path.get("description", "Exploitable sudo rule"),
                            "evidence": (
                                f"Technique: {path.get('technique')}\n"
                                f"Commands: {path.get('commands')}"
                            ),
                            "recommendation": (
                                "Restrict sudo rules to least-privilege. "
                                "Remove NOPASSWD for dangerous binaries."
                            ),
                            "chain_potential": True,
                            "confidence_score": 0.80,
                        })
            except Exception:
                logger.exception("PrivescAgent: LLM sudo analysis failed")

        await ws_progress.progress(
            self.engagement_id, "privesc.done",
            f"PrivescAgent complete — {len(findings)} findings",
        )
        self.signal_history.append(1.0 if findings else 0.4)
        return {
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "findings": findings,
        }


def _dict_to_fp(d: dict) -> OSFingerprint:
    """Reconstruct OSFingerprint from its to_dict() output (or pass-through if already an instance)."""
    if isinstance(d, OSFingerprint):
        return d
    return OSFingerprint(
        host=d.get("host", ""),
        port=d.get("port", 22),
        collected_at=d.get("collected_at", ""),
        kernel=d.get("kernel", {}),
        os_info=d.get("os_info", {}),
        packages=d.get("packages", []),
        processes=d.get("processes", []),
        open_ports=d.get("open_ports", []),
        suid_binaries=d.get("suid_binaries", []),
        users=d.get("users", []),
        groups=d.get("groups", []),
        sudo_rules=d.get("sudo_rules", []),
        cron_jobs=d.get("cron_jobs", []),
        writable_paths=d.get("writable_paths", []),
        sysctl_params=d.get("sysctl_params", {}),
        ssh_config=d.get("ssh_config", {}),
        services=d.get("services", []),
        mounts=d.get("mounts", []),
        lastlog=d.get("lastlog", []),
        collection_errors=d.get("collection_errors", []),
    )
