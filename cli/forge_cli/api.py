"""Thin HTTP client for the FORGE backend API."""
from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".forge" / "config.json"


def _load_config() -> dict:
    """Read ~/.forge/config.json; return empty dict if missing or malformed."""
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class ForgeClient:
    def __init__(self, base_url: str = "http://localhost:8080", api_key: str | None = None):
        config = _load_config()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or config.get("api_key") or os.environ.get("FORGE_API_KEY")

    def _auth_headers(self) -> dict:
        """Return base request headers, including Bearer token when an API key is set."""
        headers: dict = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, method: str, path: str, body: dict | None = None, timeout: int = 30, json_body: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        payload = json_body if json_body is not None else body
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self._auth_headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            try:
                msg = json.loads(msg).get("detail", msg)
            except Exception:
                pass
            raise APIError(e.code, msg)
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot reach FORGE backend at {self.base_url}\n"
                f"Start it with: uvicorn app.main:app --port 8080\n"
                f"({e.reason})"
            )

    def _request_bytes(self, method: str, path: str, timeout: int = 30) -> bytes:
        """Make a request and return raw response bytes (for binary downloads)."""
        url = f"{self.base_url}{path}"
        headers = self._auth_headers()
        headers["Accept"] = "application/pdf"
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            try:
                msg = json.loads(msg).get("detail", msg)
            except Exception:
                pass
            raise APIError(e.code, msg)
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot reach FORGE backend at {self.base_url}\n"
                f"Start it with: uvicorn app.main:app --port 8080\n"
                f"({e.reason})"
            )

    def health(self) -> dict:
        return self._request("GET", "/api/v1/health")

    def list_engagements(self) -> list[dict]:
        return self._request("GET", "/api/v1/engagements/")

    def get_engagement(self, eid: str) -> dict:
        return self._request("GET", f"/api/v1/engagements/{eid}")

    def create_engagement(self, target_url: str, target_type: str, target_path: str | None = None,
                          scope: list[str] | None = None, out_of_scope: list[str] | None = None) -> dict:
        body: dict = {"target_url": target_url, "target_type": target_type}
        if target_path:
            body["target_path"] = target_path
        if scope:
            body["target_scope"] = scope
        if out_of_scope:
            body["target_out_of_scope"] = out_of_scope
        return self._request("POST", "/api/v1/engagements/", body)

    def start_engagement(self, eid: str) -> dict:
        return self._request("POST", f"/api/v1/engagements/{eid}/start")

    def update_status(self, eid: str, status: str) -> dict:
        return self._request("PATCH", f"/api/v1/engagements/{eid}/status", {"status": status})

    def delete_engagement(self, eid: str) -> None:
        self._request("DELETE", f"/api/v1/engagements/{eid}")

    def gate_decide(self, eid: str, approved: bool, notes: str = "") -> dict:
        return self._request("POST", f"/api/v1/gates/{eid}/decide", {"approved": approved, "notes": notes})

    def stats(self) -> dict:
        return self._request("GET", "/api/v1/system/stats")

    def wait_for_engagement(
        self, eid: str, timeout: int = 1800, poll_interval: int = 15
    ) -> dict:
        """Poll GET /engagements/{eid} until status leaves 'running', or timeout."""
        deadline = time.monotonic() + timeout
        while True:
            eng = self.get_engagement(eid)
            if eng.get("status") != "running":
                return eng
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out after {timeout}s waiting for engagement {eid}"
                )
            time.sleep(poll_interval)

    # ── Auth ─────────────────────────────────────────────────────────────────

    def register(self, email: str, password: str, org_name: str) -> dict:
        return self._request("POST", "/api/v1/auth/register",
                             {"email": email, "password": password, "org_name": org_name})

    def login(self, email: str, password: str) -> dict:
        return self._request("POST", "/api/v1/auth/login",
                             {"email": email, "password": password})

    def me(self) -> dict:
        return self._request("GET", "/api/v1/auth/me")

    def list_api_keys(self) -> list:
        return self._request("GET", "/api/v1/auth/api-keys")

    def create_api_key(self, name: str) -> dict:
        return self._request("POST", "/api/v1/auth/api-keys", {"name": name})

    def revoke_api_key(self, key_id: str) -> None:
        self._request("DELETE", f"/api/v1/auth/api-keys/{key_id}")

    # ── Org users ─────────────────────────────────────────────────────────────

    def list_org_users(self) -> list:
        return self._request("GET", "/api/v1/org/users")

    def update_user_role(self, user_id: str, role: str) -> dict:
        return self._request("PATCH", f"/api/v1/org/users/{user_id}/role", {"role": role})

    def remove_user(self, user_id: str) -> None:
        self._request("DELETE", f"/api/v1/org/users/{user_id}")
