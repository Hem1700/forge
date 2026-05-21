# backend/app/brain/os_fingerprint.py
"""OSFingerprint dataclass — structured result of SSH host collection."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class OSFingerprint:
    host: str
    port: int
    collected_at: str                    # ISO 8601 timestamp
    kernel: dict = field(default_factory=dict)        # uname fields
    os_info: dict = field(default_factory=dict)       # /etc/os-release fields
    packages: list[dict] = field(default_factory=list)   # {name, version, arch}
    processes: list[dict] = field(default_factory=list)  # {pid, ppid, user, cmd}
    open_ports: list[dict] = field(default_factory=list) # {port, proto, process, user}
    suid_binaries: list[str] = field(default_factory=list)
    users: list[dict] = field(default_factory=list)      # from /etc/passwd
    groups: list[dict] = field(default_factory=list)     # from /etc/group
    sudo_rules: list[str] = field(default_factory=list)
    cron_jobs: list[dict] = field(default_factory=list)
    writable_paths: list[str] = field(default_factory=list)
    sysctl_params: dict = field(default_factory=dict)
    ssh_config: dict = field(default_factory=dict)
    services: list[dict] = field(default_factory=list)
    mounts: list[dict] = field(default_factory=list)
    lastlog: list[dict] = field(default_factory=list)
    collection_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
