# backend/app/swarm/agents/service_audit_agent.py
"""ServiceAuditAgent — audits SSH hardening, running services, unencrypted protocols,
and exposed management interfaces. All checks deterministic; no LLM required.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.swarm.agents.base import BaseAgent
from app.swarm.agents.privesc_agent import _dict_to_fp
from app.ws import progress as ws_progress

logger = logging.getLogger(__name__)

_UNENCRYPTED_PORTS = {
    23: "telnet",
    21: "ftp",
    513: "rsh",
    514: "rlogin",
    512: "rexec",
}

_MANAGEMENT_PORTS = {
    6379: "Redis",
    5432: "PostgreSQL",
    11211: "Memcached",
    27017: "MongoDB",
    9200: "Elasticsearch",
    2181: "ZooKeeper",
    8500: "Consul",
}

_WEAK_CIPHERS = {"3des-cbc", "aes128-cbc", "aes192-cbc", "aes256-cbc"}
_WEAK_MACS = {"hmac-md5", "hmac-md5-96", "hmac-sha1", "hmac-sha1-96",
              "umac-64@openssh.com", "hmac-ripemd160"}
_WEAK_KEX = {"diffie-hellman-group1-sha1", "diffie-hellman-group14-sha1"}

_SERVICES_NOT_ROOT = {"nginx", "apache2", "httpd", "node", "python", "python3", "ruby", "gunicorn"}


@dataclass
class ServiceAuditAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        fp = _dict_to_fp(task.get("fingerprint", {}))
        findings: list[dict] = []

        # 1. SSH hardening checks
        ssh = fp.ssh_config
        permit_root = ssh.get("PermitRootLogin", "")
        if permit_root.lower() in ("yes", "without-password", "prohibit-password"):
            findings.append(_make(
                "ssh_permit_root_login", "high",
                "SSH allows root login (PermitRootLogin is not 'no').",
                f"PermitRootLogin {permit_root}",
                "Set PermitRootLogin no in /etc/ssh/sshd_config and restart sshd.",
            ))

        # Default is "yes" when not configured
        if ssh.get("PasswordAuthentication", "yes").lower() == "yes":
            findings.append(_make(
                "ssh_password_auth", "medium",
                "SSH allows password authentication. Key-based auth is preferred.",
                f"PasswordAuthentication {ssh.get('PasswordAuthentication', 'yes (default)')}",
                "Set PasswordAuthentication no and use SSH keys only.",
            ))

        ciphers_raw = ssh.get("Ciphers", "")
        for cipher in ciphers_raw.split(","):
            if cipher.strip() in _WEAK_CIPHERS:
                findings.append(_make(
                    "ssh_weak_cipher", "medium",
                    f"SSH configured with weak cipher {cipher.strip()}.",
                    f"Ciphers {ciphers_raw}",
                    "Restrict Ciphers to chacha20-poly1305@openssh.com,aes128-gcm@openssh.com,aes256-gcm@openssh.com",
                ))
                break

        macs_raw = ssh.get("MACs", "")
        for mac in macs_raw.split(","):
            if mac.strip() in _WEAK_MACS:
                findings.append(_make(
                    "ssh_weak_mac", "medium",
                    f"SSH configured with weak MAC {mac.strip()}.",
                    f"MACs {macs_raw}",
                    "Restrict MACs to hmac-sha2-256,hmac-sha2-512 variants.",
                ))
                break

        kex_raw = ssh.get("KexAlgorithms", "")
        for kex in kex_raw.split(","):
            if kex.strip() in _WEAK_KEX:
                findings.append(_make(
                    "ssh_weak_kex", "medium",
                    f"SSH configured with weak key exchange {kex.strip()}.",
                    f"KexAlgorithms {kex_raw}",
                    "Remove DH group1/group14 SHA1 KEX algorithms from KexAlgorithms.",
                ))
                break

        await ws_progress.progress(
            self.engagement_id, "service_audit.ssh_done",
            f"SSH checks: {len(findings)} findings so far",
        )

        # 2. Services running as root
        root_cmds: set[str] = set()
        for p in fp.processes:
            if p.get("user") == "root":
                cmd = p.get("cmd", "").split()[0].rstrip(":") if p.get("cmd") else ""
                if cmd:
                    root_cmds.add(cmd.split("/")[-1])

        listening_procs: set[str] = set()
        for port_entry in fp.open_ports:
            proc = port_entry.get("process", "").strip("()")
            if "/" in proc:
                proc = proc.split("/")[-1]
            listening_procs.add(proc)

        for svc in _SERVICES_NOT_ROOT:
            if svc in root_cmds and svc in listening_procs:
                findings.append(_make(
                    "service_running_as_root", "high",
                    f"{svc} is listening on a port and running as root. Compromise gives immediate root access.",
                    f"Process: {svc}, User: root",
                    f"Run {svc} as a dedicated non-privileged user (e.g., www-data).",
                ))

        # 3. Unencrypted protocols
        for port_entry in fp.open_ports:
            local = port_entry.get("local", "")
            port_num = _extract_port(local)
            if port_num in _UNENCRYPTED_PORTS:
                proto_name = _UNENCRYPTED_PORTS[port_num]
                # Only flag non-loopback
                if not local.startswith("127.") and not local.startswith("[::1]"):
                    findings.append(_make(
                        "unencrypted_protocol", "high",
                        f"Unencrypted protocol {proto_name} (port {port_num}) is listening on a non-loopback interface.",
                        f"Local address: {local}, Process: {port_entry.get('process', 'unknown')}",
                        f"Disable {proto_name} and migrate to SSH or TLS equivalents.",
                    ))

        # 4. Exposed management interfaces
        for port_entry in fp.open_ports:
            local = port_entry.get("local", "")
            port_num = _extract_port(local)
            if port_num in _MANAGEMENT_PORTS:
                svc_name = _MANAGEMENT_PORTS[port_num]
                # Flag if binding on 0.0.0.0 or :: (all interfaces)
                if "0.0.0.0" in local or local.startswith(":::") or local.startswith("[::]:"):
                    findings.append(_make(
                        "exposed_management_interface", "high",
                        f"{svc_name} management interface is exposed on all interfaces (port {port_num}).",
                        f"Local: {local}, Process: {port_entry.get('process', 'unknown')}",
                        f"Bind {svc_name} to 127.0.0.1 only, or restrict access with firewall rules.",
                    ))

        await ws_progress.progress(
            self.engagement_id, "service_audit.done",
            f"ServiceAuditAgent complete — {len(findings)} findings",
        )
        self.signal_history.append(1.0 if findings else 0.4)
        return {
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "findings": findings,
        }


def _extract_port(local: str) -> int:
    """Extract port number from 'addr:port' string."""
    try:
        return int(local.rsplit(":", 1)[-1])
    except (ValueError, IndexError):
        return 0


def _make(vuln: str, severity: str, desc: str, evidence: str, rec: str) -> dict:
    return {
        "vulnerability": vuln,
        "severity": severity,
        "description": desc,
        "evidence": evidence,
        "recommendation": rec,
        "confidence_score": 0.90,
    }
