# backend/app/swarm/agents/network_exposure_agent.py
"""NetworkExposureAgent — maps externally reachable services, flags unauthenticated
management interfaces, and identifies services running as root on public interfaces.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.swarm.agents.base import BaseAgent
from app.swarm.agents.privesc_agent import _dict_to_fp
from app.ws import progress as ws_progress

logger = logging.getLogger(__name__)

# Services that should never bind on 0.0.0.0 as root without auth
_UNAUTHENTICATED_MGMT = {
    6379: "Redis",
    11211: "Memcached",
    27017: "MongoDB",
    9200: "Elasticsearch",
    2181: "ZooKeeper",
}

_MGMT_PORTS = set(_UNAUTHENTICATED_MGMT) | {5432, 8500, 3306, 1521}


@dataclass
class NetworkExposureAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        fp_dict = task.get("fingerprint", {})
        fp = _dict_to_fp(fp_dict)
        findings: list[dict] = []

        # Build set of root-owned processes (by command name)
        root_cmds: set[str] = set()
        for p in fp.processes:
            if p.get("user") == "root":
                cmd = p.get("cmd", "").split()[0].rstrip(":")
                root_cmds.add(cmd.split("/")[-1])

        for port_entry in fp.open_ports:
            local = port_entry.get("local", "")
            process = port_entry.get("process", "")
            user = port_entry.get("user", "")
            port_num = _extract_port(local)
            is_public = _is_public_binding(local)

            # 1. External exposure matrix: service binding on 0.0.0.0 as root
            if is_public and (user == "root" or _process_is_root(process, root_cmds)):
                findings.append({
                    "vulnerability": "root_service_exposed",
                    "severity": "high",
                    "description": f"Service '{process}' is listening on a public interface as root. Compromise leads to immediate root access.",
                    "evidence": f"Port: {local}, Process: {process}, User: {user or 'root (inferred)'}",
                    "recommendation": f"Run '{process}' as a non-privileged user. Use setuid/setgid drops or dedicated service accounts.",
                    "confidence_score": 0.85,
                })

            # 2. Cross-correlation: public + root + unauthenticated management service → CRITICAL
            if is_public and port_num in _UNAUTHENTICATED_MGMT and (user == "root" or _process_is_root(process, root_cmds)):
                svc_name = _UNAUTHENTICATED_MGMT[port_num]
                findings.append({
                    "vulnerability": "unauthenticated_root_service",
                    "severity": "critical",
                    "description": f"{svc_name} is publicly accessible, running as root, and likely unauthenticated. Any attacker with network access can gain full control.",
                    "evidence": f"Port: {local}, Service: {svc_name}, Process: {process}",
                    "recommendation": f"Bind {svc_name} to 127.0.0.1, enable authentication, and run as a non-root user.",
                    "confidence_score": 0.95,
                    "chain_potential": True,
                })

        # 3. IPv6 exposure where IPv4 equivalent is loopback-only
        ipv4_public: set[int] = set()
        ipv4_loopback: set[int] = set()
        ipv6_public: dict[int, dict] = {}

        for port_entry in fp.open_ports:
            local = port_entry.get("local", "")
            port_num = _extract_port(local)
            if "0.0.0.0" in local:
                ipv4_public.add(port_num)
            elif "127.0.0.1" in local:
                ipv4_loopback.add(port_num)
            elif local.startswith(":::") or local.startswith("[::]:"):
                ipv6_public[port_num] = port_entry

        for port_num, entry in ipv6_public.items():
            if port_num in ipv4_loopback and port_num not in ipv4_public:
                findings.append({
                    "vulnerability": "ipv6_exposure_bypass",
                    "severity": "medium",
                    "description": f"Port {port_num} is restricted to IPv4 loopback but exposed on IPv6 (::). IPv6 firewall rules may not cover this.",
                    "evidence": f"IPv4: 127.0.0.1:{port_num}, IPv6: {entry.get('local')}, Process: {entry.get('process')}",
                    "recommendation": "Apply equivalent firewall rules to IPv6 interfaces, or bind the service to ::1 (IPv6 loopback) instead of ::.",
                    "confidence_score": 0.80,
                })

        await ws_progress.progress(
            self.engagement_id, "network_exposure.done",
            f"NetworkExposureAgent complete — {len(findings)} findings",
        )
        self.signal_history.append(1.0 if findings else 0.4)
        return {
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "findings": findings,
        }


def _extract_port(local: str) -> int:
    try:
        return int(local.rsplit(":", 1)[-1])
    except (ValueError, IndexError):
        return 0


def _is_public_binding(local: str) -> bool:
    return "0.0.0.0" in local or local.startswith(":::") or local.startswith("[::]:") or local.startswith("*:")


def _process_is_root(process: str, root_cmds: set[str]) -> bool:
    name = process.strip("()").split("/")[-1]
    return any(name.startswith(rc) or rc.startswith(name) for rc in root_cmds)
