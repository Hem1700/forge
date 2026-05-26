# backend/app/swarm/agents/config_audit_agent.py
"""ConfigAuditAgent (OS) — checks sysctl hardening, PAM config, mount options,
and kernel security parameters for a live Linux host.

Distinct from config_auditor.py which audits Dockerfile/K8s/nginx files.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.swarm.agents.base import BaseAgent
from app.swarm.agents.privesc_agent import _dict_to_fp
from app.ws import progress as ws_progress

logger = logging.getLogger(__name__)


@dataclass
class ConfigAuditAgent(BaseAgent):

    async def _execute(self, task: dict) -> dict:
        fp_dict = task.get("fingerprint", {})
        fp = _dict_to_fp(fp_dict)
        # pam_config may be injected as extra key not in OSFingerprint dataclass
        pam_config: dict = fp_dict.get("pam_config", {})
        findings: list[dict] = []

        sc = fp.sysctl_params

        # ASLR
        if sc.get("kernel.randomize_va_space", "2") != "2":
            findings.append(_make(
                "aslr_disabled", "high",
                f"ASLR is disabled or partially disabled (kernel.randomize_va_space={sc.get('kernel.randomize_va_space')}).",
                f"kernel.randomize_va_space = {sc.get('kernel.randomize_va_space')}",
                "Set kernel.randomize_va_space = 2 in /etc/sysctl.conf.",
            ))

        # Core dumps for SUID binaries
        if sc.get("fs.suid_dumpable", "0") != "0":
            findings.append(_make(
                "suid_dumpable_enabled", "medium",
                f"Core dumps enabled for SUID binaries (fs.suid_dumpable={sc.get('fs.suid_dumpable')}). May expose sensitive memory.",
                f"fs.suid_dumpable = {sc.get('fs.suid_dumpable')}",
                "Set fs.suid_dumpable = 0 in /etc/sysctl.conf.",
            ))

        # ptrace scope
        ptrace = sc.get("kernel.yama.ptrace_scope", "1")
        if ptrace == "0":
            findings.append(_make(
                "ptrace_unrestricted", "medium",
                "ptrace is unrestricted (kernel.yama.ptrace_scope=0). Any process can ptrace any other process owned by the same user.",
                "kernel.yama.ptrace_scope = 0",
                "Set kernel.yama.ptrace_scope = 1 or higher in /etc/sysctl.conf.",
            ))

        # IP forwarding
        if sc.get("net.ipv4.ip_forward", "0") == "1":
            findings.append(_make(
                "ip_forwarding_enabled", "medium",
                "IP forwarding is enabled (net.ipv4.ip_forward=1). This host is acting as a router.",
                "net.ipv4.ip_forward = 1",
                "Disable IP forwarding if this host is not a router: net.ipv4.ip_forward = 0",
            ))

        # ICMP redirects
        if sc.get("net.ipv4.conf.all.accept_redirects", "0") == "1":
            findings.append(_make(
                "icmp_redirects_accepted", "low",
                "Host accepts ICMP redirects, which can be abused to redirect traffic.",
                "net.ipv4.conf.all.accept_redirects = 1",
                "Set net.ipv4.conf.all.accept_redirects = 0 in /etc/sysctl.conf.",
            ))

        # SYN cookies
        if sc.get("net.ipv4.tcp_syncookies", "1") == "0":
            findings.append(_make(
                "syn_cookies_disabled", "medium",
                "TCP SYN cookies are disabled. The host is more vulnerable to SYN flood DoS attacks.",
                "net.ipv4.tcp_syncookies = 0",
                "Enable SYN cookies: net.ipv4.tcp_syncookies = 1 in /etc/sysctl.conf.",
            ))

        await ws_progress.progress(
            self.engagement_id, "config_audit.sysctl_done",
            f"sysctl checks complete — {len(findings)} issues",
        )

        # /tmp without noexec
        for mount in fp.mounts:
            mp = mount.get("mountpoint", "")
            opts = mount.get("options", "")
            if mp in ("/tmp", "/var/tmp", "/dev/shm") and "noexec" not in opts:
                findings.append(_make(
                    "tmp_noexec_missing", "medium",
                    f"{mp} is mounted without the noexec option. Attackers can place and execute binaries in {mp}.",
                    f"Mount: {mount}",
                    f"Remount {mp} with noexec: add noexec to its entry in /etc/fstab.",
                ))

        # NFS no_root_squash (also checked by PrivescAgent, but surfaced here as config issue)
        for mount in fp.mounts:
            if mount.get("fstype") == "nfs" and "no_root_squash" in mount.get("options", ""):
                findings.append(_make(
                    "nfs_no_root_squash", "high",
                    f"NFS mount {mount.get('mountpoint')} uses no_root_squash — remote root maps to local root.",
                    f"Mount: {mount}",
                    "Add root_squash to the NFS export in /etc/exports and re-export.",
                ))

        # PAM lockout policy
        if pam_config:
            common_auth = pam_config.get("common-auth", "") or pam_config.get("sshd", "")
            if common_auth and "pam_faillock" not in common_auth and "pam_tally" not in common_auth:
                findings.append(_make(
                    "pam_no_lockout", "high",
                    "No account lockout policy found in PAM configuration (missing pam_faillock or pam_tally2). Brute-force attacks are unrestricted.",
                    f"common-auth config: {common_auth[:200]}",
                    "Configure pam_faillock in /etc/pam.d/common-auth to lock accounts after repeated failures.",
                ))

        await ws_progress.progress(
            self.engagement_id, "config_audit.done",
            f"ConfigAuditAgent complete — {len(findings)} findings",
        )
        self.signal_history.append(1.0 if findings else 0.4)
        return {
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "findings": findings,
        }


def _make(vuln: str, severity: str, desc: str, evidence: str, rec: str) -> dict:
    return {
        "vulnerability": vuln,
        "severity": severity,
        "description": desc,
        "evidence": evidence,
        "recommendation": rec,
        "confidence_score": 0.90,
    }
