# backend/app/brain/os_modeler.py
"""OSModeler — connects via SSH, collects system fingerprint in parallel."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.brain.os_fingerprint import OSFingerprint

logger = logging.getLogger(__name__)


@dataclass
class SSHAuth:
    auth_type: Literal["key", "password", "agent"]
    key_path: str | None = None
    password: str | None = None


class OSModeler:
    """Agentless SSH collector. Runs 20+ read-only commands in parallel."""

    async def collect(self, host: str, port: int, username: str, auth: SSHAuth) -> OSFingerprint:
        import asyncssh

        connect_kwargs: dict = {"host": host, "port": port, "username": username, "known_hosts": None}
        if auth.auth_type == "password" and auth.password:
            connect_kwargs["password"] = auth.password
        elif auth.auth_type == "key" and auth.key_path:
            connect_kwargs["client_keys"] = [auth.key_path]
        # agent: asyncssh uses SSH agent by default when no key/password given

        fp = OSFingerprint(
            host=host,
            port=port,
            collected_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                await self._collect_all(conn, fp)
        except Exception as e:
            logger.exception("SSH connection failed for %s:%d", host, port)
            fp.collection_errors.append(f"ssh_connect: {e}")

        return fp

    async def _run(self, conn, cmd: str) -> str:
        try:
            result = await conn.run(cmd, check=False, timeout=15)
            return result.stdout or ""
        except Exception as e:
            return f"__ERROR__:{e}"

    async def _collect_all(self, conn, fp: OSFingerprint) -> None:
        commands = {
            "uname":     "uname -a",
            "os_release": "cat /etc/os-release 2>/dev/null || cat /etc/redhat-release 2>/dev/null || echo ''",
            "packages_deb": "dpkg -l 2>/dev/null | tail -n +6 | awk '{print $2,$3,$4}'",
            "packages_rpm": "rpm -qa --qf '%{NAME} %{VERSION} %{ARCH}\n' 2>/dev/null || echo ''",
            "ps":        "ps axf -o pid,ppid,user,comm 2>/dev/null || ps aux 2>/dev/null",
            "ss":        "ss -tlnup 2>/dev/null || netstat -tlnup 2>/dev/null || echo ''",
            "suid":      "find / -perm -4000 -type f 2>/dev/null | head -100",
            "passwd":    "cat /etc/passwd 2>/dev/null || echo ''",
            "group":     "cat /etc/group 2>/dev/null || echo ''",
            "sudoers":   "sudo cat /etc/sudoers 2>/dev/null || sudo -l 2>/dev/null || echo ''",
            "crontab":   "crontab -l 2>/dev/null || echo ''",
            "cron_d":    "ls /etc/cron.d/ 2>/dev/null | head -50 && cat /etc/cron.d/* 2>/dev/null | head -200",
            "sysctl":    "sysctl -a 2>/dev/null | head -200",
            "sshd_cfg":  "cat /etc/ssh/sshd_config 2>/dev/null || echo ''",
            "services":  "systemctl list-units --type=service --state=running --no-pager 2>/dev/null | head -100 || service --status-all 2>/dev/null || echo ''",
            "mounts":    "cat /proc/mounts 2>/dev/null || mount 2>/dev/null || echo ''",
            "writable":  "find /tmp /var/tmp /dev/shm -writable -type d 2>/dev/null | head -50",
            "lastlog":   "lastlog 2>/dev/null | head -50 || last -n 20 2>/dev/null || echo ''",
            "env":       "env 2>/dev/null | grep -v 'PASS\\|SECRET\\|KEY\\|TOKEN' | head -50",
            "id":        "id && groups",
        }

        results = await asyncio.gather(
            *[self._run(conn, cmd) for cmd in commands.values()],
            return_exceptions=True,
        )
        data = dict(zip(commands.keys(), results))

        self._parse_uname(data.get("uname", ""), fp)
        self._parse_os_release(data.get("os_release", ""), fp)
        self._parse_packages(data.get("packages_deb", ""), data.get("packages_rpm", ""), fp)
        self._parse_ps(data.get("ps", ""), fp)
        self._parse_ss(data.get("ss", ""), fp)
        self._parse_suid(data.get("suid", ""), fp)
        self._parse_passwd(data.get("passwd", ""), fp)
        self._parse_group(data.get("group", ""), fp)
        self._parse_sudo(data.get("sudoers", ""), fp)
        self._parse_cron(data.get("crontab", ""), data.get("cron_d", ""), fp)
        self._parse_sysctl(data.get("sysctl", ""), fp)
        self._parse_sshd(data.get("sshd_cfg", ""), fp)
        self._parse_services(data.get("services", ""), fp)
        self._parse_mounts(data.get("mounts", ""), fp)
        self._parse_writable(data.get("writable", ""), fp)
        self._parse_lastlog(data.get("lastlog", ""), fp)

        for key, val in data.items():
            if isinstance(val, Exception) or (isinstance(val, str) and val.startswith("__ERROR__:")):
                fp.collection_errors.append(f"{key}: {val}")

    # ── Parsers ───────────────────────────────────────────────────────────────

    def _parse_uname(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        parts = raw.strip().split()
        if len(parts) >= 3:
            fp.kernel = {
                "raw": raw.strip(),
                "os": parts[0] if parts else "",
                "hostname": parts[1] if len(parts) > 1 else "",
                "release": parts[2] if len(parts) > 2 else "",
                "machine": parts[-1] if parts else "",
            }

    def _parse_os_release(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        info = {}
        for line in raw.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip().strip('"')
        fp.os_info = info

    def _parse_packages(self, deb_raw: str, rpm_raw: str, fp: OSFingerprint) -> None:
        pkgs = []
        if deb_raw and not deb_raw.startswith("__ERROR__"):
            for line in deb_raw.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    pkgs.append({"name": parts[0], "version": parts[1], "arch": parts[2] if len(parts) > 2 else ""})
        if rpm_raw and not rpm_raw.startswith("__ERROR__") and not pkgs:
            for line in rpm_raw.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    pkgs.append({"name": parts[0], "version": parts[1], "arch": parts[2] if len(parts) > 2 else ""})
        fp.packages = pkgs[:500]  # cap

    def _parse_ps(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        procs = []
        for line in raw.splitlines()[1:]:
            parts = line.split(None, 3)
            if len(parts) >= 4:
                procs.append({"pid": parts[0], "ppid": parts[1], "user": parts[2], "cmd": parts[3]})
        fp.processes = procs[:200]

    def _parse_ss(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        ports = []
        for line in raw.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                ports.append({"proto": parts[0], "local": parts[4], "process": parts[-1] if len(parts) > 5 else ""})
        fp.open_ports = ports[:100]

    def _parse_suid(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        fp.suid_binaries = [l.strip() for l in raw.splitlines() if l.strip()]

    def _parse_passwd(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        users = []
        for line in raw.splitlines():
            parts = line.split(":")
            if len(parts) >= 7:
                users.append({"username": parts[0], "uid": parts[2], "gid": parts[3], "home": parts[5], "shell": parts[6]})
        fp.users = users

    def _parse_group(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        groups = []
        for line in raw.splitlines():
            parts = line.split(":")
            if len(parts) >= 4:
                groups.append({"name": parts[0], "gid": parts[2], "members": parts[3].split(",") if parts[3] else []})
        fp.groups = groups

    def _parse_sudo(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        fp.sudo_rules = [l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]

    def _parse_cron(self, crontab_raw: str, cron_d_raw: str, fp: OSFingerprint) -> None:
        jobs = []
        for raw in [crontab_raw, cron_d_raw]:
            if not raw or raw.startswith("__ERROR__"):
                continue
            for line in raw.splitlines():
                if line.strip() and not line.strip().startswith("#"):
                    jobs.append({"schedule": line.strip()})
        fp.cron_jobs = jobs

    def _parse_sysctl(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        params = {}
        for line in raw.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                params[k.strip()] = v.strip()
        fp.sysctl_params = params

    def _parse_sshd(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        cfg = {}
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(None, 1)
                if len(parts) == 2:
                    cfg[parts[0]] = parts[1]
        fp.ssh_config = cfg

    def _parse_services(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        svcs = []
        for line in raw.splitlines():
            parts = line.split()
            if parts and parts[0].endswith(".service"):
                svcs.append({"name": parts[0], "state": parts[2] if len(parts) > 2 else "unknown"})
        fp.services = svcs

    def _parse_mounts(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        mounts = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                mounts.append({"device": parts[0], "mountpoint": parts[1], "fstype": parts[2], "options": parts[3]})
        fp.mounts = mounts

    def _parse_writable(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        fp.writable_paths = [l.strip() for l in raw.splitlines() if l.strip()]

    def _parse_lastlog(self, raw: str, fp: OSFingerprint) -> None:
        if not raw or raw.startswith("__ERROR__"):
            return
        entries = []
        for line in raw.splitlines()[1:]:
            parts = line.split()
            if parts:
                entries.append({"username": parts[0], "port": parts[1] if len(parts) > 1 else "", "from": parts[2] if len(parts) > 2 else "", "latest": " ".join(parts[3:]) if len(parts) > 3 else ""})
        fp.lastlog = entries
