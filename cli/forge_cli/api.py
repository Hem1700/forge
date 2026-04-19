"""Thin HTTP client for the FORGE backend API."""
from __future__ import annotations
import urllib.request
import urllib.error
import json
from typing import Any


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class ForgeClient:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None, timeout: int = 30, json_body: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        payload = json_body if json_body is not None else body
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
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
        req = urllib.request.Request(url, method=method)
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
